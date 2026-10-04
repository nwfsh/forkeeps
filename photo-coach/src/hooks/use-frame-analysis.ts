import type { CameraView } from 'expo-camera';
import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';
import { useCallback, useEffect, useRef, useState, type RefObject } from 'react';

import { analyzeFrame, type Analysis } from '@/lib/server';

/** Frames are downscaled to this width before upload; plenty for face landmarks. */
const FRAME_WIDTH = 480;
/** Minimum gap between frames, so the phone isn't flat out. */
const MIN_INTERVAL_MS = 150;

export type FrameAnalysisState = {
  analysis: Analysis | null;
  error: string | null;
  /** Analyses per second over the last few frames. */
  fps: number;
};

/**
 * Repeatedly snapshots the camera, sends a small copy to the server, and
 * exposes the latest result. One frame is in flight at a time.
 * `capture` takes a real full-quality photo, waiting for any in-flight
 * snapshot first, since the camera can only take one picture at a time.
 */
export function useFrameAnalysis(cameraRef: RefObject<CameraView | null>, enabled: boolean) {
  const [state, setState] = useState<FrameAnalysisState>({ analysis: null, error: null, fps: 0 });
  const timestamps = useRef<number[]>([]);
  const busyRef = useRef(false);
  const snapshotRef = useRef<Promise<unknown>>(Promise.resolve());

  const capture = useCallback(async () => {
    if (!cameraRef.current || busyRef.current) return null;
    busyRef.current = true;
    try {
      await snapshotRef.current;
      return await cameraRef.current.takePictureAsync({ quality: 0.9 });
    } finally {
      busyRef.current = false;
    }
  }, [cameraRef]);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    const controller = new AbortController();

    async function loop() {
      while (!cancelled) {
        const started = Date.now();
        try {
          if (cameraRef.current && !busyRef.current) {
            const pending = snapshot(cameraRef.current);
            snapshotRef.current = pending.catch(() => {});
            const uri = await pending;
            if (cancelled) return;
            const analysis = await analyzeFrame(uri, controller.signal);
            if (cancelled) return;

            const now = Date.now();
            timestamps.current = [...timestamps.current.slice(-4), now];
            const span = (now - timestamps.current[0]) / 1000;
            const fps = span > 0 ? (timestamps.current.length - 1) / span : 0;
            setState({ analysis, error: null, fps });
          }
        } catch (e) {
          if (cancelled) return;
          setState((s) => ({ ...s, error: e instanceof Error ? e.message : String(e) }));
          // Back off so an unreachable server doesn't spin the loop.
          await sleep(1000);
        }
        await sleep(Math.max(0, MIN_INTERVAL_MS - (Date.now() - started)));
      }
    }

    loop();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [cameraRef, enabled]);

  return { ...state, capture };
}

async function snapshot(camera: CameraView): Promise<string> {
  const photo = await camera.takePictureAsync({ quality: 0.5, shutterSound: false });
  const rendered = await ImageManipulator.manipulate(photo.uri)
    .resize({ width: FRAME_WIDTH, height: null })
    .renderAsync();
  const saved = await rendered.saveAsync({ format: SaveFormat.JPEG, compress: 0.7 });
  return saved.uri;
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
