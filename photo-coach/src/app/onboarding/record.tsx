import { CameraView, type CameraType } from 'expo-camera';
import { router } from 'expo-router';
import { SymbolView } from 'expo-symbols';
import { useEffect, useRef, useState } from 'react';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useOnboarding, type Snapshot } from '@/components/onboarding-provider';
import { INK, MUTED, StepDots } from '@/components/onboarding-style';
import { snapshot } from '@/hooks/use-frame-analysis';
import { analyzeFrame, pickSnapshots } from '@/lib/server';

const RECORD_SECONDS = 20;
// A 3-2-1 before recording, so they're settled by the time frames are kept.
const COUNTDOWN_SECONDS = 3;
const TICK_MS = 250;
// Shortest gap between frames while recording; taking one takes a few hundred ms on top.
const FRAME_GAP_MS = 150;
// Frames sent to the server at once after recording.
const UPLOADS_AT_ONCE = 4;

// Pinch zoom: expo-camera's zoom is a share of the lens's maximum on a log scale, and the maximum
// isn't exposed, so this assumes a typical 16x; ZOOM_LIMIT keeps it to about 4x of digital zoom.
const ASSUMED_MAX_ZOOM = 16;
const ZOOM_LIMIT = 0.5;
// Pinching this far out on the main lens switches to the ultra wide, and this far in back, as the
// iPhone camera does.
const TO_ULTRA_WIDE = 0.75;
const TO_WIDE = 1.4;

// Where this screen sits in onboarding: name, record, compare.
const STEP = 2;
const STEPS = 3;
const CREAM = '#F7F4EE';
const ROSE = '#C9466F';

type Phase = 'intro' | 'countdown' | 'recording' | 'analysing';

/** Seconds as m:ss. */
function clock(seconds: number) {
  const whole = Math.floor(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`;
}

/**
 * Onboarding's recording: twenty seconds of just being on camera, after a 3-2-1. Frames are only
 * taken while recording, so a slow connection can't make it choppy; afterwards they're analysed
 * in parallel and the server picks about twenty varied snapshots to compare (server/snapshots.py). There are no
 * prompts: natural movement gives enough variety, and the server finds the different moments.
 * It starts on the back camera, since someone else filming gives the most realistic photos;
 * the front camera's photos aren't mirrored either, so left and right measure the same.
 */
export default function RecordScreen() {
  const cameraRef = useRef<CameraView>(null);
  const [facing, setFacing] = useState<CameraType>('back');
  const [phase, setPhase] = useState<Phase>('intro');
  const [elapsed, setElapsed] = useState(0);
  const [countdown, setCountdown] = useState(COUNTDOWN_SECONDS);
  const [error, setError] = useState<string | null>(null);
  // Small copies of the frames taken while recording, oldest first.
  const frames = useRef<string[]>([]);
  // A copy for rendering: the ref fills up while recording without re-rendering each time.
  const [frameCount, setFrameCount] = useState(0);
  const [analysed, setAnalysed] = useState(0);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const recording = useRef(false);
  // The frame-taking loop, so analysis waits for its last frame.
  const capturing = useRef<Promise<void>>(Promise.resolve());
  const { setSnapshots } = useOnboarding();
  const insets = useSafeAreaInsets();
  // The back camera's lenses: the main one for 1x and the ultra wide, if there is one, for 0.5x.
  const [lenses, setLenses] = useState<{ wide?: string; ultraWide?: string }>({});
  const [ultraWide, setUltraWide] = useState(false);
  const [zoom, setZoom] = useState(0);
  // Where the current pinch started.
  const [pinchFrom, setPinchFrom] = useState({ zoom: 0, ultraWide: false });

  // Stop the countdown and the camera loop if the screen closes mid-recording.
  useEffect(
    () => () => {
      if (timer.current) clearInterval(timer.current);
      recording.current = false;
    },
    [],
  );

  /** Takes small frames as fast as the camera allows until recording stops. */
  async function captureFrames() {
    while (recording.current && cameraRef.current) {
      const started = Date.now();
      try {
        const frame = await snapshot(cameraRef.current);
        if (!recording.current) break;
        frames.current.push(frame);
        setFrameCount(frames.current.length);
      } catch {
        // A frame the camera couldn't take is just skipped.
      }
      await new Promise((resolve) =>
        setTimeout(resolve, Math.max(0, FRAME_GAP_MS - (Date.now() - started))),
      );
    }
  }

  function start() {
    setError(null);
    setCountdown(COUNTDOWN_SECONDS);
    setPhase('countdown');
    let left = COUNTDOWN_SECONDS;
    timer.current = setInterval(() => {
      left -= 1;
      setCountdown(left);
      if (left <= 0) {
        if (timer.current) clearInterval(timer.current);
        record();
      }
    }, 1000);
  }

  /** The record button: starts, cancels the countdown, or stops early and uses what was filmed. */
  function press() {
    if (phase === 'intro') start();
    else if (phase === 'countdown') {
      if (timer.current) clearInterval(timer.current);
      setPhase('intro');
    } else if (phase === 'recording') {
      if (timer.current) clearInterval(timer.current);
      recording.current = false;
      pick();
    }
  }

  function record() {
    frames.current = [];
    setFrameCount(0);
    setElapsed(0);
    setPhase('recording');
    recording.current = true;
    capturing.current = captureFrames();
    let ticks = 0;
    timer.current = setInterval(() => {
      ticks += 1;
      const seconds = (ticks * TICK_MS) / 1000;
      setElapsed(seconds);
      if (seconds >= RECORD_SECONDS) {
        if (timer.current) clearInterval(timer.current);
        recording.current = false;
        pick();
      }
    }, TICK_MS);
  }

  /** Analyses every frame, a few at a time; frames with exactly one face are kept. */
  async function analyseFrames(uris: string[]): Promise<Snapshot[]> {
    const kept: Snapshot[] = [];
    let next = 0;
    let done = 0;
    setAnalysed(0);
    async function worker() {
      while (next < uris.length) {
        const index = next++;
        try {
          const analysis = await analyzeFrame(uris[index]);
          // Only frames with exactly one face can say anything about this person's taste.
          if (analysis.faces.length === 1)
            kept.push({ id: String(index), uri: uris[index], analysis });
        } catch {
          // A frame that couldn't be analysed is just left out.
        }
        setAnalysed(++done);
      }
    }
    await Promise.all(Array.from({ length: UPLOADS_AT_ONCE }, worker));
    return kept.sort((a, b) => Number(a.id) - Number(b.id));
  }

  async function pick() {
    setPhase('analysing');
    await capturing.current;
    try {
      const taken = await analyseFrames(frames.current);
      const { snapshots, usable } = await pickSnapshots(taken);
      if (snapshots.length === 0) {
        setError(
          `Only ${usable} usable frame${usable === 1 ? '' : 's'}. Keep your whole face in view, in good light, ` +
            'and try again.',
        );
        setPhase('intro');
        return;
      }
      const byId = new Map(taken.map((frame) => [frame.id, frame]));
      setSnapshots(snapshots.flatMap((id) => byId.get(id) ?? []));
      router.push('/onboarding/compare');
      setPhase('intro');
    } catch (e) {
      setError(`Couldn't reach the server. ${e instanceof Error ? e.message : String(e)}`);
      setPhase('intro');
    }
  }

  const busy = phase === 'countdown' || phase === 'recording';
  const lens = facing === 'back' ? (ultraWide ? lenses.ultraWide : lenses.wide) : undefined;
  const canGoWide = facing === 'back' && !!lenses.ultraWide;

  function pickLens(wide: boolean) {
    setUltraWide(wide);
    setZoom(0);
  }

  const pinch = Gesture.Pinch()
    .runOnJS(true)
    .onStart(() => {
      setPinchFrom({ zoom, ultraWide });
    })
    .onUpdate(({ scale }) => {
      const from = pinchFrom;
      if (!from.ultraWide && from.zoom === 0 && canGoWide && scale < TO_ULTRA_WIDE) {
        if (!ultraWide) pickLens(true);
        return;
      }
      if (from.ultraWide && scale > TO_WIDE) {
        if (ultraWide) pickLens(false);
        return;
      }
      if (from.ultraWide) return;
      const next = from.zoom + Math.log(scale) / Math.log(ASSUMED_MAX_ZOOM);
      setZoom(Math.min(ZOOM_LIMIT, Math.max(0, next)));
    });

  return (
    <View style={styles.screen}>
      <View style={[styles.header, { paddingTop: insets.top + 16 }]}>
        <View style={styles.stepDots}>
          <StepDots step={STEP} steps={STEPS} />
        </View>
        <Text style={styles.title}>Record a {RECORD_SECONDS} second clip</Text>
        <Text style={styles.subtitle}>Move naturally: turn, smile, look away.</Text>
      </View>

      <GestureDetector gesture={pinch}>
        <View style={styles.cameraBox}>
          <CameraView
            ref={cameraRef}
            style={StyleSheet.absoluteFill}
            facing={facing}
            animateShutter={false}
            selectedLens={lens}
            zoom={ultraWide ? 0 : zoom}
            onAvailableLensesChanged={({ lenses: available }) => {
              if (facing !== 'back') return;
              setLenses({
                wide: available.find((l) => !/ultra|tele|dual|triple/i.test(l)),
                ultraWide: available.find((l) => /ultra wide/i.test(l)),
              });
            }}
          />

          {phase === 'countdown' && (
            <View style={styles.overlay} pointerEvents="none">
              <Text style={styles.bigCount}>{Math.max(1, countdown)}</Text>
            </View>
          )}

          <View style={styles.card}>
            {phase === 'analysing' ? (
              <View style={styles.cardRow}>
                <ActivityIndicator color={INK} />
                <Text style={styles.cardText}>
                  {analysed < frameCount
                    ? `Analysing ${analysed} of ${frameCount} frames…`
                    : 'Picking your snapshots…'}
                </Text>
              </View>
            ) : (
              <>
                <View style={styles.cardRow}>
                  {phase === 'recording' && <View style={styles.liveDot} />}
                  <Text style={styles.time}>
                    {clock(phase === 'recording' ? elapsed : 0)} / {clock(RECORD_SECONDS)}
                  </Text>
                </View>
                <View style={styles.track}>
                  <View
                    style={[
                      styles.bar,
                      { width: `${Math.min(1, elapsed / RECORD_SECONDS) * 100}%` },
                      phase !== 'recording' && styles.barHidden,
                    ]}
                  />
                </View>
                {phase === 'intro' && (
                  <Text style={styles.hint}>
                    {error ??
                      (facing === 'back'
                        ? 'Best with someone else filming you.'
                        : 'Hold the phone at eye level.')}
                  </Text>
                )}
              </>
            )}
          </View>
        </View>
      </GestureDetector>

      <View style={[styles.controls, { paddingBottom: insets.bottom + 12 }]}>
        {/* The lenses, as on the iPhone camera: 0.5x is the ultra wide, 1x the main lens (and
            resets a pinch zoom). The front camera has just the one. */}
        <View style={styles.zoomRow}>
          {canGoWide && (
            <View style={styles.zoom}>
              {(
                [
                  ['0.5', true],
                  ['1×', false],
                ] as const
              ).map(([label, wide]) => {
                const selected = ultraWide === wide;
                return (
                  <Pressable
                    key={label}
                    accessibilityRole="button"
                    accessibilityLabel={wide ? 'Zoom out to 0.5x' : '1x'}
                    accessibilityState={{ selected }}
                    onPress={() => pickLens(wide)}
                    hitSlop={6}
                    style={[styles.zoomOption, selected && styles.zoomSelected]}>
                    <Text style={[styles.zoomText, selected && styles.zoomTextSelected]}>
                      {label}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
          )}
        </View>

        <View style={styles.buttons}>
          <View style={styles.side}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Back"
              disabled={busy || phase === 'analysing'}
              onPress={() => router.back()}
              hitSlop={8}
              style={[styles.round, (busy || phase === 'analysing') && styles.dimmed]}>
              <SymbolView
                name={{ ios: 'chevron.left', android: 'arrow_back', web: 'arrow_back' }}
                size={20}
                weight="semibold"
                tintColor={INK}
              />
            </Pressable>
          </View>
          {/* Not waiting for the camera's ready signal: it doesn't always come again after
              flipping cameras, the 3-2-1 gives it time to start, and frames it can't take yet
              are skipped. */}
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={busy ? 'Stop' : 'Start recording'}
            disabled={phase === 'analysing'}
            onPress={press}
            style={styles.shutter}>
            <View style={busy ? styles.stop : styles.record} />
          </Pressable>
          <View style={styles.side}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={facing === 'back' ? 'Film yourself' : 'Someone else films'}
              disabled={busy || phase === 'analysing'}
              onPress={() => {
                setFacing((f) => (f === 'back' ? 'front' : 'back'));
                pickLens(false);
              }}
              hitSlop={8}
              style={[styles.round, (busy || phase === 'analysing') && styles.dimmed]}>
              <SymbolView
                name={{
                  ios: 'arrow.triangle.2.circlepath.camera',
                  android: 'flip_camera_ios',
                  web: 'flip_camera_ios',
                }}
                size={22}
                tintColor={INK}
              />
            </Pressable>
          </View>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: '#FFFFFF',
  },
  header: {
    backgroundColor: CREAM,
    paddingHorizontal: 20,
    paddingBottom: 20,
    gap: 6,
  },
  stepDots: {
    marginBottom: 12,
  },
  title: {
    color: INK,
    fontSize: 30,
    lineHeight: 36,
    fontWeight: '700',
    letterSpacing: -0.5,
  },
  subtitle: {
    color: MUTED,
    fontSize: 17,
    lineHeight: 23,
  },
  cameraBox: {
    flex: 1,
    backgroundColor: '#000',
    overflow: 'hidden',
  },
  overlay: {
    ...StyleSheet.absoluteFill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  bigCount: {
    color: '#fff',
    fontSize: 120,
    fontWeight: '800',
    textShadowColor: 'rgba(0,0,0,0.5)',
    textShadowRadius: 12,
  },
  card: {
    position: 'absolute',
    left: 12,
    right: 12,
    bottom: 16,
    paddingVertical: 16,
    paddingHorizontal: 20,
    gap: 14,
    borderRadius: 20,
    backgroundColor: 'rgba(255,255,255,0.85)',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(255,255,255,0.9)',
  },
  cardRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
  },
  liveDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: ROSE,
  },
  time: {
    color: INK,
    fontSize: 24,
    fontWeight: '600',
    fontVariant: ['tabular-nums'],
  },
  cardText: {
    color: INK,
    fontSize: 16,
  },
  track: {
    height: 4,
    borderRadius: 2,
    backgroundColor: 'rgba(26,26,26,0.12)',
    overflow: 'hidden',
  },
  bar: {
    height: 4,
    backgroundColor: ROSE,
  },
  barHidden: {
    width: 0,
  },
  hint: {
    color: MUTED,
    fontSize: 14,
    textAlign: 'center',
  },
  controls: {
    paddingTop: 12,
    paddingHorizontal: 24,
    gap: 14,
    backgroundColor: '#FFFFFF',
  },
  zoomRow: {
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  buttons: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  side: {
    flex: 1,
    alignItems: 'center',
  },
  shutter: {
    width: 92,
    height: 92,
    borderRadius: 46,
    borderWidth: 3,
    borderColor: INK,
    alignItems: 'center',
    justifyContent: 'center',
  },
  record: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: ROSE,
  },
  stop: {
    width: 38,
    height: 38,
    borderRadius: 8,
    backgroundColor: INK,
  },
  zoom: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    padding: 3,
    borderRadius: 999,
    backgroundColor: '#F2EEEB',
  },
  zoomOption: {
    minWidth: 38,
    height: 34,
    paddingHorizontal: 8,
    borderRadius: 17,
    alignItems: 'center',
    justifyContent: 'center',
  },
  zoomSelected: {
    backgroundColor: INK,
  },
  zoomText: {
    color: MUTED,
    fontSize: 14,
  },
  zoomTextSelected: {
    color: '#FFFFFF',
    fontWeight: '600',
  },
  round: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: '#F2EEEB',
    alignItems: 'center',
    justifyContent: 'center',
  },
  dimmed: {
    opacity: 0.35,
  },
});
