import type { CameraView, PictureRef } from 'expo-camera';
import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';
import { useCallback, useEffect, useRef, useState, type RefObject } from 'react';

import { analyzeFrame, type Analysis } from '@/lib/server';

/** Frames are downscaled to this width before upload; plenty for face landmarks. */
const FRAME_WIDTH = 480;
/** Minimum gap between frames, so the phone isn't flat out. */
const MIN_INTERVAL_MS = 150;
/** Longest a snapshot or an upload may take before the loop gives up on it and tries again. */
const STEP_TIMEOUT_MS = 5000;

/** Pause between burst shots; each takePictureAsync takes a few hundred ms on top. */
const BURST_GAP_MS = 80;

export type FrameAnalysisState = {
  analysis: Analysis | null;
  /** The small frame `analysis` describes, kept on the phone in the cache. */
  frameUri: string | null;
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
export function useFrameAnalysis(
  cameraRef: RefObject<CameraView | null>,
  enabled: boolean,
  /** Called with every new analysis and the frame it describes, e.g. to auto-capture. */
  onFrame?: (analysis: Analysis, frameUri: string) => void,
) {
  const [state, setState] = useState<FrameAnalysisState>({
    analysis: null,
    frameUri: null,
    error: null,
    fps: 0,
  });
  const timestamps = useRef<number[]>([]);
  // The latest callback, so the loop doesn't restart whenever the screen re-renders.
  const onFrameRef = useRef(onFrame);
  useEffect(() => {
    onFrameRef.current = onFrame;
  });
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

  /**
   * Takes `count` full-quality photos back to back (only the first makes a shutter sound),
   * pausing the analysis loop throughout. Returns their URIs; fewer if the camera goes away.
   */
  const captureBurst = useCallback(
    async (count: number) => {
      if (!cameraRef.current || busyRef.current) return [];
      busyRef.current = true;
      const uris: string[] = [];
      try {
        await snapshotRef.current;
        for (let i = 0; i < count && cameraRef.current; i++) {
          const photo = await cameraRef.current.takePictureAsync({
            quality: 0.9,
            shutterSound: i === 0,
          });
          uris.push(photo.uri);
          if (i < count - 1) await sleep(BURST_GAP_MS);
        }
        return uris;
      } finally {
        busyRef.current = false;
      }
    },
    [cameraRef],
  );

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    const controller = new AbortController();

    async function loop() {
      while (!cancelled) {
        const started = Date.now();
        try {
          if (cameraRef.current && !busyRef.current) {
            const pending = withTimeout(snapshot(cameraRef.current), 'Taking the snapshot');
            snapshotRef.current = pending.catch(() => {});
            const uri = await pending;
            if (cancelled) return;
            // Each upload gets its own timeout; unmounting still aborts it.
            const request = new AbortController();
            const abort = () => request.abort();
            controller.signal.addEventListener('abort', abort);
            const timer = setTimeout(abort, STEP_TIMEOUT_MS);
            let analysis: Analysis;
            try {
              analysis = await analyzeFrame(uri, request.signal);
            } catch (e) {
              throw request.signal.aborted && !controller.signal.aborted
                ? new Error('Uploading the frame timed out')
                : e;
            } finally {
              clearTimeout(timer);
              controller.signal.removeEventListener('abort', abort);
            }
            if (cancelled) return;

            const now = Date.now();
            timestamps.current = [...timestamps.current.slice(-4), now];
            const span = (now - timestamps.current[0]) / 1000;
            const fps = span > 0 ? (timestamps.current.length - 1) / span : 0;
            setState({ analysis, frameUri: uri, error: null, fps });
            onFrameRef.current?.(analysis, uri);
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

  return { ...state, capture, captureBurst };
}

/**
 * A small frame from the camera. The full-size picture stays in memory as a reference instead of
 * being written to a file first, which is most of the time a frame takes on the phone.
 */
export async function snapshot(camera: CameraView): Promise<string> {
  const picture = await camera.takePictureAsync({
    quality: 0.5,
    shutterSound: false,
    pictureRef: true,
  });
  return shrink(picture);
}

/** A small copy of a photo (a file or an in-memory picture), the size the server analyses frames at. */
export async function shrink(source: string | PictureRef): Promise<string> {
  const rendered = await ImageManipulator.manipulate(source)
    .resize({ width: FRAME_WIDTH, height: null })
    .renderAsync();
  const saved = await rendered.saveAsync({ format: SaveFormat.JPEG, compress: 0.7 });
  return saved.uri;
}

/** Rejects if the promise hasn't settled within STEP_TIMEOUT_MS, naming the step. */
function withTimeout<T>(promise: Promise<T>, step: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`${step} timed out`)), STEP_TIMEOUT_MS);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        clearTimeout(timer);
        reject(error);
      },
    );
  });
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
