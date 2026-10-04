import { CameraView, useCameraPermissions, type CameraType } from 'expo-camera';
import { Image } from 'expo-image';
import { router, useIsFocused } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { Alert, Animated, Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { FaceOverlay } from '@/components/face-overlay';
import { usePhotos } from '@/components/photos-provider';
import { BottomTabInset, Spacing } from '@/constants/theme';
import { useFrameAnalysis } from '@/hooks/use-frame-analysis';
import { useVoiceCoach } from '@/hooks/use-voice-coach';
import { BURST_SIZE, rankBurst } from '@/lib/burst';
import { redFlagMessage, SERVER_URL, type Analysis } from '@/lib/server';
import { GOOD_CLIP } from '@/lib/voice';

const WIDE_LENS = 'builtInWideAngleCamera';
// Auto-capture fires after this many perfect frames in a row (about half a second), then
// waits AUTO_COOLDOWN_MS before it can fire again, so one good moment gives one burst.
const STEADY_FRAMES = 2;
const AUTO_COOLDOWN_MS = 4000;
const NOTICE_MS = 3000;

export default function CameraScreen() {
  const [permission, requestPermission] = useCameraPermissions();
  const isFocused = useIsFocused();
  const cameraRef = useRef<CameraView>(null);
  const { photos: all, add } = usePhotos();
  // As on the Photos tab: burst alternates stay out of sight until kept in review.
  const photos = all.filter((p) => !p.alternate || p.kept);

  const [ready, setReady] = useState(false);
  const [facing, setFacing] = useState<CameraType>('back');
  const [lenses, setLenses] = useState<string[]>([]);
  const [ultraWide, setUltraWide] = useState(false);
  const [layout, setLayout] = useState({ width: 0, height: 0 });
  const [capturing, setCapturing] = useState(false);
  const [flash] = useState(() => new Animated.Value(0));
  // Burst: the shutter takes BURST_SIZE shots and keeps the best. Auto: fires a burst by itself
  // once the shot has been perfect for STEADY_FRAMES frames in a row.
  const [burstMode, setBurstMode] = useState(false);
  const [auto, setAuto] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const perfectStreak = useRef(0);
  const lastAutoAt = useRef(0);
  const busy = useRef(false);
  // Set below once takeBurst exists; the frame loop calls it with every analysis.
  const onFrameRef = useRef<(frame: Analysis) => void>(() => {});

  const { analysis, error, fps, capture, captureBurst } = useFrameAnalysis(cameraRef, ready && isFocused, (frame) =>
    onFrameRef.current(frame)
  );
  // The line for the tip on screen: first why the photo can't be judged at all (nobody there, face
  // cut off or covered), then a framing or lighting warning, then the change the profile's taste
  // model wants, then praise when there's nothing left to fix.
  const instruction = analysis?.shot?.instruction ?? null;
  const redFlag = analysis?.red_flags?.[0];
  // Red flags are spoken by their code; ones a voice has no line for stay quiet (useVoiceCoach
  // skips clips it doesn't have), rather than saying "looks good".
  const clip =
    !isFocused || error || !analysis
      ? null
      : (redFlag ?? analysis.warnings[0]?.clip ?? instruction?.clip ?? GOOD_CLIP);
  const voice = useVoiceCoach(clip);

  // iOS reports lens names like "Back Ultra Wide Camera"; only the back camera has one.
  const ultraWideLens = lenses.find((l) => /ultra\s*wide/i.test(l));
  const selectedLens = facing === 'back' && ultraWide && ultraWideLens ? ultraWideLens : WIDE_LENS;

  function showFlash() {
    flash.setValue(1);
    Animated.timing(flash, { toValue: 0, duration: 250, useNativeDriver: true }).start();
  }

  function showNotice(text: string) {
    setNotice(text);
    setTimeout(() => setNotice((current) => (current === text ? null : current)), NOTICE_MS);
  }

  async function takePhoto() {
    if (burstMode) return takeBurst('shutter');
    if (busy.current) return;
    busy.current = true;
    setCapturing(true);
    // Remember what the coach saw at the moment of the press, not after the capture delay.
    const seen = analysis;
    showFlash();
    try {
      const photo = await capture();
      if (photo) add(photo.uri, seen);
    } catch (e) {
      Alert.alert('Photo failed', e instanceof Error ? e.message : String(e));
    } finally {
      busy.current = false;
      setCapturing(false);
    }
  }

  /** Takes a burst, keeps the best shot, and leaves the rest for review as alternates. */
  async function takeBurst(trigger: 'shutter' | 'auto') {
    if (busy.current) return;
    busy.current = true;
    setCapturing(true);
    showFlash();
    try {
      const uris = await captureBurst(BURST_SIZE);
      if (!uris.length) return;
      setNotice(`Picking the best of ${uris.length}…`);
      const [best, ...rest] = await rankBurst(uris);
      const burst = String(Date.now());
      for (const shot of rest) add(shot.uri, shot.analysis, { burst, alternate: true });
      add(best.uri, best.analysis, { burst });
      showNotice(
        `${trigger === 'auto' ? 'Auto shot: kept' : 'Kept'} the best of ${uris.length}` +
          (rest.length ? ` · ${rest.length} more in Review` : '')
      );
    } catch (e) {
      setNotice(null);
      Alert.alert('Burst failed', e instanceof Error ? e.message : String(e));
    } finally {
      busy.current = false;
      setCapturing(false);
    }
  }

  /** Counts perfect frames in a row and fires a burst once there are enough. */
  function onFrame(frame: Analysis) {
    perfectStreak.current = frame.shot?.perfect ? perfectStreak.current + 1 : 0;
    const rested = Date.now() - lastAutoAt.current > AUTO_COOLDOWN_MS;
    if (auto && !busy.current && rested && perfectStreak.current >= STEADY_FRAMES) {
      perfectStreak.current = 0;
      lastAutoAt.current = Date.now();
      takeBurst('auto');
    }
  }

  function flip() {
    setReady(false);
    setFacing((f) => (f === 'back' ? 'front' : 'back'));
  }

  useEffect(() => {
    onFrameRef.current = onFrame;
  });

  if (!permission) return <View style={styles.fill} />;

  if (!permission.granted) {
    return (
      <SafeAreaView style={[styles.fill, styles.center]}>
        <Text style={styles.message}>Photo Coach needs the camera to see your shot.</Text>
        <Pressable style={styles.pill} onPress={requestPermission}>
          <Text style={styles.pillText}>Allow camera</Text>
        </Pressable>
      </SafeAreaView>
    );
  }

  // The error can come from taking the snapshot as well as from the network, so show it.
  const tip = error
    ? `Can't reach ${SERVER_URL} (${error})`
    : redFlag
      ? redFlagMessage(redFlag)
      : (analysis?.warnings[0]?.message ?? instruction?.message);

  return (
    <View
      style={styles.fill}
      onLayout={(e) => setLayout(e.nativeEvent.layout)}>
      {isFocused && (
        <CameraView
          // A new camera per side: onCameraReady only fires once per mount, and the frame
          // loop waits for it again after a flip.
          key={facing}
          ref={cameraRef}
          style={StyleSheet.absoluteFill}
          facing={facing}
          selectedLens={selectedLens}
          animateShutter={false}
          onCameraReady={() => setReady(true)}
          onAvailableLensesChanged={(e) => setLenses(e.lenses)}
        />
      )}

      {analysis && layout.width > 0 && (
        <FaceOverlay
          analysis={analysis}
          viewWidth={layout.width}
          viewHeight={layout.height}
          mirrored={facing === 'front'}
        />
      )}

      <Animated.View style={[StyleSheet.absoluteFill, styles.flash, { opacity: flash }]} pointerEvents="none" />

      <SafeAreaView style={styles.hud} pointerEvents="box-none">
        <View style={styles.topRow}>
          {tip ? (
            <View style={[styles.tip, error && styles.tipError]}>
              <Text style={styles.tipText}>{tip}</Text>
            </View>
          ) : (
            analysis && (
              <View style={[styles.tip, styles.tipGood]}>
                <Text style={styles.tipText}>Looks good</Text>
              </View>
            )
          )}
          {error && <Text style={styles.stats}>{error}</Text>}
          {analysis && !error && (
            <Text style={styles.stats}>
              {analysis.faces.length} face{analysis.faces.length === 1 ? '' : 's'} · {fps.toFixed(1)} fps ·{' '}
              {analysis.ms} ms
              {analysis.shot?.scored_by === 'model'
                ? ` · style match ${Math.round(analysis.shot.score * 100)}%`
                : ''}
            </Text>
          )}
          {notice ? (
            <View style={[styles.tip, styles.tipNotice]}>
              <Text style={styles.tipText}>{notice}</Text>
            </View>
          ) : (
            auto &&
            analysis?.shot?.perfect &&
            !capturing && (
              <View style={[styles.tip, styles.tipGood]}>
                <Text style={styles.tipText}>Perfect: hold still…</Text>
              </View>
            )
          )}
          {voice.canSpeak && (
            <Pressable accessibilityLabel="Change coach voice" style={styles.pill} onPress={voice.next}>
              <Text style={styles.pillText}>{voice.persona ? `Voice: ${voice.persona.name}` : 'Voice off'}</Text>
            </Pressable>
          )}
        </View>

        <View style={styles.modes}>
          <Pressable
            accessibilityLabel="Take the photo automatically when it's perfect"
            accessibilityState={{ selected: auto }}
            style={[styles.pill, auto && styles.pillOn]}
            onPress={() => setAuto((a) => !a)}>
            <Text style={styles.pillText}>Auto {auto ? 'on' : 'off'}</Text>
          </Pressable>
          <Pressable
            accessibilityLabel={`Burst: take ${BURST_SIZE} and keep the best`}
            accessibilityState={{ selected: burstMode }}
            style={[styles.pill, burstMode && styles.pillOn]}
            onPress={() => setBurstMode((b) => !b)}>
            <Text style={styles.pillText}>Burst {burstMode ? 'on' : 'off'}</Text>
          </Pressable>
          <Pressable
            accessibilityLabel="Find your best angles"
            style={styles.pill}
            onPress={() => router.push('/angles')}>
            <Text style={styles.pillText}>Angles</Text>
          </Pressable>
        </View>

        <View style={styles.controls}>
          <View style={styles.side}>
            {photos[0] && (
              <Pressable accessibilityLabel="View photos" onPress={() => router.navigate('/photos')}>
                <Image source={{ uri: photos[0].uri }} style={styles.thumb} />
                <View style={styles.badge}>
                  <Text style={styles.badgeText}>{photos.length}</Text>
                </View>
              </Pressable>
            )}
          </View>

          <Pressable
            accessibilityLabel="Take photo"
            disabled={capturing}
            style={({ pressed }) => [styles.shutter, (pressed || capturing) && styles.shutterPressed]}
            onPress={takePhoto}
          />

          <View style={[styles.side, styles.sideRight]}>
            {facing === 'back' && ultraWideLens && (
              <Pressable style={styles.pill} onPress={() => setUltraWide((u) => !u)}>
                <Text style={styles.pillText}>{ultraWide ? '0.5x' : '1x'}</Text>
              </Pressable>
            )}
            <Pressable style={styles.pill} onPress={flip}>
              <Text style={styles.pillText}>Flip</Text>
            </Pressable>
          </View>
        </View>
      </SafeAreaView>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: {
    flex: 1,
    backgroundColor: '#000',
  },
  center: {
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.three,
    padding: Spacing.four,
  },
  message: {
    color: '#fff',
    fontSize: 17,
    textAlign: 'center',
  },
  hud: {
    flex: 1,
    justifyContent: 'space-between',
    paddingBottom: BottomTabInset + Spacing.three,
  },
  topRow: {
    alignItems: 'center',
    gap: Spacing.two,
    paddingTop: Spacing.two,
  },
  tip: {
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two,
    borderRadius: 999,
    backgroundColor: 'rgba(0,0,0,0.6)',
  },
  tipGood: {
    backgroundColor: 'rgba(22,163,74,0.75)',
  },
  tipError: {
    backgroundColor: 'rgba(220,38,38,0.8)',
  },
  tipText: {
    color: '#fff',
    fontSize: 17,
    fontWeight: '600',
  },
  stats: {
    color: 'rgba(255,255,255,0.8)',
    fontSize: 12,
    fontVariant: ['tabular-nums'],
  },
  modes: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: Spacing.two,
    marginBottom: Spacing.three,
  },
  pillOn: {
    backgroundColor: 'rgba(22,163,74,0.85)',
  },
  tipNotice: {
    backgroundColor: 'rgba(37,99,235,0.8)',
  },
  controls: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: Spacing.four,
  },
  side: {
    flex: 1,
    flexDirection: 'row',
    gap: Spacing.two,
  },
  sideRight: {
    justifyContent: 'flex-end',
  },
  shutter: {
    width: 72,
    height: 72,
    borderRadius: 36,
    borderWidth: 5,
    borderColor: '#fff',
    backgroundColor: 'rgba(255,255,255,0.3)',
  },
  shutterPressed: {
    backgroundColor: 'rgba(255,255,255,0.7)',
  },
  thumb: {
    width: 48,
    height: 48,
    borderRadius: 8,
    borderWidth: 2,
    borderColor: '#fff',
  },
  badge: {
    position: 'absolute',
    top: -6,
    right: -6,
    minWidth: 20,
    height: 20,
    paddingHorizontal: 5,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#fff',
  },
  badgeText: {
    color: '#000',
    fontSize: 12,
    fontWeight: '700',
  },
  flash: {
    backgroundColor: '#fff',
  },
  pill: {
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two,
    borderRadius: 999,
    backgroundColor: 'rgba(0,0,0,0.5)',
  },
  pillText: {
    color: '#fff',
    fontWeight: '600',
  },
});
