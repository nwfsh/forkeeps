import { CameraView, useCameraPermissions } from 'expo-camera';
import { Image } from 'expo-image';
import { router } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, FlatList, Pressable, StyleSheet, Text, useWindowDimensions, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { RetrainBanner } from '@/components/retrain-banner';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing } from '@/constants/theme';
import { useFrameAnalysis } from '@/hooks/use-frame-analysis';
import { clusterAngles, sendVerdict, type Analysis, type AngleCluster } from '@/lib/server';

const RECORD_SECONDS = 12;
const TICK_MS = 250;
// What to do while recording, one prompt per slice of the time, so the frames cover the angles.
const PROMPTS = [
  'Look straight at the camera',
  'Slowly turn to your left',
  'Now slowly to your right',
  'Chin up a little',
  'Chin down a little',
  'Tilt your head to one side',
];
const GREEN = '#3DDC84';

type Frame = { id: string; uri: string; analysis: Analysis };
type Phase = 'intro' | 'recording' | 'grouping' | 'choose' | 'saving' | 'done';

/**
 * The angle finder: film yourself turning your head for a few seconds, then pick the angles
 * you like from one typical frame per angle. The picks only teach the taste model about head
 * angle (the server blanks everything else), since these frames are small and often blurry.
 */
export default function AnglesScreen() {
  const [permission, requestPermission] = useCameraPermissions();
  const cameraRef = useRef<CameraView>(null);
  const [ready, setReady] = useState(false);
  const [phase, setPhase] = useState<Phase>('intro');
  const [elapsed, setElapsed] = useState(0);
  const [clusters, setClusters] = useState<AngleCluster[]>([]);
  const [liked, setLiked] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const frames = useRef<Frame[]>([]);
  // Copies for rendering: the ref fills up while recording, without re-rendering each time.
  const [frameCount, setFrameCount] = useState(0);
  const [captured, setCaptured] = useState<Frame[]>([]);
  const timers = useRef<ReturnType<typeof setInterval>[]>([]);
  const { width } = useWindowDimensions();

  const { error: frameError } = useFrameAnalysis(cameraRef, ready && phase === 'recording', (analysis, uri) => {
    // Only frames with exactly one measured head can say anything about angle.
    if (analysis.faces.length === 1 && analysis.faces[0].pose) {
      frames.current.push({ id: String(frames.current.length), uri, analysis });
      setFrameCount(frames.current.length);
    }
  });

  // Stop the countdown if the screen closes mid-recording.
  useEffect(() => () => timers.current.forEach(clearInterval), []);

  function start() {
    frames.current = [];
    setFrameCount(0);
    setError(null);
    setLiked(new Set());
    setElapsed(0);
    setPhase('recording');
    let ticks = 0;
    const tick = setInterval(() => {
      ticks += 1;
      const seconds = (ticks * TICK_MS) / 1000;
      setElapsed(seconds);
      if (seconds >= RECORD_SECONDS) {
        clearInterval(tick);
        group();
      }
    }, TICK_MS);
    timers.current = [tick];
  }

  async function group() {
    setPhase('grouping');
    const taken = frames.current;
    setCaptured(taken);
    try {
      const result = await clusterAngles(taken.map(({ id, analysis }) => ({ id, analysis })));
      if (result.clusters.length < 2) {
        setError(
          `Only caught ${taken.length} usable frame${taken.length === 1 ? '' : 's'} at ` +
            `${result.clusters.length} angle${result.clusters.length === 1 ? '' : 's'}. ` +
            'Keep your face in view and turn a bit further.'
        );
        setPhase('intro');
        return;
      }
      setClusters(result.clusters);
      setPhase('choose');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPhase('intro');
    }
  }

  function toggle(frame: string) {
    setLiked((current) => {
      const next = new Set(current);
      if (next.has(frame)) next.delete(frame);
      else next.add(frame);
      return next;
    });
  }

  async function save() {
    setPhase('saving');
    setError(null);
    const session = String(Date.now());
    try {
      for (const cluster of clusters) {
        const frame = captured.find((f) => f.id === cluster.frame);
        if (!frame) continue;
        await sendVerdict(
          `angle-${session}-${cluster.frame}`,
          liked.has(cluster.frame) ? 'keep' : 'remove',
          frame.analysis,
          'angle'
        );
      }
      setPhase('done');
    } catch (e) {
      setError(`Couldn't save your picks. ${e instanceof Error ? e.message : String(e)}`);
      setPhase('choose');
    }
  }

  if (!permission) return <ThemedView style={styles.fill} />;
  if (!permission.granted) {
    return (
      <ThemedView style={[styles.fill, styles.center]}>
        <ThemedText style={styles.centerText}>The angle finder needs the camera.</ThemedText>
        <Pressable style={styles.button} onPress={requestPermission}>
          <Text style={styles.buttonText}>Allow camera</Text>
        </Pressable>
      </ThemedView>
    );
  }

  const filming = phase === 'intro' || phase === 'recording' || phase === 'grouping';
  const prompt = PROMPTS[Math.min(PROMPTS.length - 1, Math.floor((elapsed / RECORD_SECONDS) * PROMPTS.length))];
  const cardWidth = (width - Spacing.three * 3) / 2;
  // Learning needs at least one angle liked and one not.
  const canSave = liked.size > 0 && liked.size < clusters.length;

  return (
    <ThemedView style={styles.fill}>
      {filming && (
        <CameraView ref={cameraRef} style={StyleSheet.absoluteFill} facing="front" animateShutter={false}
          onCameraReady={() => setReady(true)} />
      )}
      <SafeAreaView style={styles.fill} pointerEvents="box-none">
        <View style={styles.header}>
          <Text style={[styles.title, !filming && styles.titleThemed]}>Find your angles</Text>
          <Pressable onPress={() => router.back()} hitSlop={12} style={styles.close}>
            <Text style={styles.closeText}>Done</Text>
          </Pressable>
        </View>

        {phase === 'intro' && (
          <View style={styles.bottom}>
            <View style={styles.panel}>
              <Text style={styles.panelText}>
                For {RECORD_SECONDS} seconds, slowly turn your head left, right, up and down while the
                camera watches. Then pick the angles you like best.
              </Text>
              {error && <Text style={styles.error}>{error}</Text>}
            </View>
            <Pressable style={[styles.button, !ready && styles.disabled]} disabled={!ready} onPress={start}>
              <Text style={styles.buttonText}>{error ? 'Try again' : 'Start'}</Text>
            </Pressable>
          </View>
        )}

        {phase === 'recording' && (
          <View style={styles.bottom}>
            <View style={styles.panel}>
              <Text style={styles.prompt}>{prompt}</Text>
              <Text style={styles.panelText}>
                {Math.max(0, Math.ceil(RECORD_SECONDS - elapsed))}s · {frameCount} frames
                {frameError ? ` · ${frameError}` : ''}
              </Text>
            </View>
          </View>
        )}

        {phase === 'grouping' && (
          <View style={[styles.bottom, styles.center]}>
            <ActivityIndicator color="#fff" />
            <Text style={styles.panelText}>Grouping {frameCount} frames by angle…</Text>
          </View>
        )}

        {(phase === 'choose' || phase === 'saving') && (
          <View style={styles.fill}>
            <ThemedText type="small" themeColor="textSecondary" style={styles.hint}>
              Tap every angle you like. The ones you leave count as ones you don&apos;t.
            </ThemedText>
            <FlatList
              data={clusters}
              keyExtractor={(c) => c.frame}
              numColumns={2}
              columnWrapperStyle={styles.gridRow}
              contentContainerStyle={styles.grid}
              renderItem={({ item }) => {
                const uri = captured.find((f) => f.id === item.frame)?.uri;
                const on = liked.has(item.frame);
                return (
                  <Pressable
                    accessibilityRole="checkbox"
                    accessibilityState={{ checked: on }}
                    accessibilityLabel={item.label}
                    onPress={() => toggle(item.frame)}
                    style={[styles.card, { width: cardWidth }, on && styles.cardOn]}>
                    {uri && <Image source={{ uri }} style={styles.cardImage} contentFit="cover" />}
                    <View style={styles.cardLabel}>
                      <Text style={styles.cardText}>{on ? '♥ ' : ''}{item.label}</Text>
                      <Text style={styles.cardSub}>{item.size} frames</Text>
                    </View>
                  </Pressable>
                );
              }}
            />
            {error && <Text style={styles.error}>{error}</Text>}
            <View style={styles.footer}>
              <Pressable style={[styles.button, (!canSave || phase === 'saving') && styles.disabled]}
                disabled={!canSave || phase === 'saving'} onPress={save}>
                {phase === 'saving' ? <ActivityIndicator color="#0B2E19" /> : (
                  <Text style={styles.buttonText}>
                    {canSave ? `Save ${liked.size} favourite${liked.size === 1 ? '' : 's'}` : 'Pick some, not all'}
                  </Text>
                )}
              </Pressable>
            </View>
          </View>
        )}

        {phase === 'done' && (
          <View style={styles.fill}>
            <ThemedText style={styles.doneText}>
              Saved. You liked {liked.size} of {clusters.length} angles; the coach learns from these next
              time it retrains.
            </ThemedText>
            <RetrainBanner />
            <View style={styles.footer}>
              <Pressable style={styles.button} onPress={() => router.back()}>
                <Text style={styles.buttonText}>Back to the camera</Text>
              </Pressable>
            </View>
          </View>
        )}
      </SafeAreaView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  fill: {
    flex: 1,
  },
  center: {
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.three,
  },
  centerText: {
    textAlign: 'center',
    paddingHorizontal: Spacing.four,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: Spacing.three,
  },
  title: {
    color: '#fff',
    fontSize: 20,
    fontWeight: '700',
    textShadowColor: 'rgba(0,0,0,0.6)',
    textShadowRadius: 4,
  },
  titleThemed: {
    color: '#888',
    textShadowRadius: 0,
  },
  close: {
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two,
    borderRadius: 999,
    backgroundColor: 'rgba(0,0,0,0.5)',
  },
  closeText: {
    color: '#fff',
    fontWeight: '600',
  },
  bottom: {
    flex: 1,
    justifyContent: 'flex-end',
    padding: Spacing.three,
    gap: Spacing.three,
  },
  panel: {
    padding: Spacing.three,
    borderRadius: Spacing.three,
    backgroundColor: 'rgba(0,0,0,0.6)',
    gap: Spacing.two,
  },
  panelText: {
    color: '#fff',
    fontSize: 15,
  },
  prompt: {
    color: '#fff',
    fontSize: 24,
    fontWeight: '700',
  },
  error: {
    color: '#F87171',
    textAlign: 'center',
    paddingHorizontal: Spacing.three,
  },
  hint: {
    paddingHorizontal: Spacing.three,
    paddingBottom: Spacing.two,
  },
  grid: {
    gap: Spacing.three,
    padding: Spacing.three,
  },
  gridRow: {
    gap: Spacing.three,
  },
  card: {
    borderRadius: Spacing.three,
    overflow: 'hidden',
    borderWidth: 3,
    borderColor: 'transparent',
    backgroundColor: '#222',
  },
  cardOn: {
    borderColor: GREEN,
  },
  cardImage: {
    width: '100%',
    aspectRatio: 3 / 4,
  },
  cardLabel: {
    padding: Spacing.two,
    backgroundColor: 'rgba(0,0,0,0.75)',
  },
  cardText: {
    color: '#fff',
    fontWeight: '700',
  },
  cardSub: {
    color: 'rgba(255,255,255,0.7)',
    fontSize: 12,
  },
  footer: {
    padding: Spacing.three,
    alignItems: 'center',
  },
  button: {
    alignSelf: 'center',
    minWidth: 200,
    alignItems: 'center',
    paddingHorizontal: Spacing.four,
    paddingVertical: Spacing.three,
    borderRadius: 999,
    backgroundColor: GREEN,
  },
  buttonText: {
    color: '#0B2E19',
    fontWeight: '700',
    fontSize: 16,
  },
  disabled: {
    opacity: 0.5,
  },
  doneText: {
    padding: Spacing.three,
  },
});
