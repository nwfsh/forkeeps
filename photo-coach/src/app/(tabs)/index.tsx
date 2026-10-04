import { CameraView, useCameraPermissions, type CameraType } from 'expo-camera';
import { Image } from 'expo-image';
import { router, useIsFocused } from 'expo-router';
import { SymbolView } from 'expo-symbols';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Animated, Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { FaceOverlay } from '@/components/face-overlay';
import { ACCENT, INK } from '@/components/onboarding-style';
import { usePhotos } from '@/components/photos-provider';
import { Spacing, FontFamily } from '@/constants/theme';
import { useFrameAnalysis } from '@/hooks/use-frame-analysis';
import { useMakeupReminder } from '@/hooks/use-makeup-reminder';
import { useVoiceCoach } from '@/hooks/use-voice-coach';
import { BURST_SIZE, rankBurst } from '@/lib/burst';
import {
  currentPerson,
  mainRedFlag,
  redFlagMessage,
  SERVER_URL,
  type Analysis,
} from '@/lib/server';
import { GOOD_CLIP, nameClip } from '@/lib/voice';

const WIDE_LENS = 'builtInWideAngleCamera';
// Auto-capture fires after this many perfect frames in a row (about half a second), then
// waits AUTO_COOLDOWN_MS before it can fire again, so one good moment gives one burst.
const STEADY_FRAMES = 2;
const AUTO_COOLDOWN_MS = 4000;
const NOTICE_MS = 3000;
// Once the coach has said their name in a group, it isn't said again until the group has been
// gone this long (a frame or two seeing only one face doesn't count as the group breaking up).
const GROUP_GONE_MS = 10000;

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
  const makeup = useMakeupReminder();
  // In a group the coach says the profile's name before its first tip, so they know it's for
  // them; after that tips carry on as usual until the group breaks up.
  const [named, setNamed] = useState(false);
  const lastGroupAt = useRef(0);
  const onNameSaid = useCallback(() => setNamed(true), []);

  const { analysis, error, fps, capture, captureBurst } = useFrameAnalysis(
    cameraRef,
    ready && isFocused,
    (frame) => onFrameRef.current(frame),
  );
  // The line for the tip on screen: first why the photo can't be judged at all (nobody there, face
  // cut off or covered), then a makeup reminder against their makeup look (colour that's off is
  // the first thing people notice), then a framing or lighting warning, then the change the
  // profile's taste model wants, then praise when there's nothing left to fix.
  const instruction = analysis?.shot?.instruction ?? null;
  const redFlag = analysis ? mainRedFlag(analysis) : null;
  // Red flags are spoken by their own line; one a voice has no line for stays quiet
  // (useVoiceCoach skips clips it doesn't have), rather than saying "looks good".
  const clip =
    !isFocused || error || !analysis
      ? null
      : redFlag
        ? redFlag.clip
        : (makeup.tip?.clip ?? analysis.warnings[0]?.clip ?? instruction?.clip ?? GOOD_CLIP);
  const inGroup = analysis?.subject === 'found';
  const voice = useVoiceCoach(clip, inGroup && !named ? nameClip() : null, onNameSaid);

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
          (rest.length ? ` · ${rest.length} more in Review` : ''),
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
    makeup.onFrame(frame);
    if (frame.subject === 'found') lastGroupAt.current = Date.now();
    else if (named && Date.now() - lastGroupAt.current > GROUP_GONE_MS) setNamed(false);
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

  /** In a group, a tip starts with the profile's name: "Avery, tilt your chin down a little". */
  function forThem(message: string | undefined) {
    if (!message || !inGroup) return message;
    const person = currentPerson();
    return `${person.charAt(0).toUpperCase()}${person.slice(1)}, ${message.charAt(0).toLowerCase()}${message.slice(1)}`;
  }

  // The error can come from taking the snapshot as well as from the network, so show it.
  const tip = error
    ? `Can't reach ${SERVER_URL} (${error})`
    : redFlag
      ? redFlagMessage(redFlag.flag, analysis?.subject)
      : forThem(makeup.tip?.message ?? analysis?.warnings[0]?.message ?? instruction?.message);

  return (
    <View style={styles.fill} onLayout={(e) => setLayout(e.nativeEvent.layout)}>
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

      <Animated.View
        style={[StyleSheet.absoluteFill, styles.flash, { opacity: flash }]}
        pointerEvents="none"
      />

      <SafeAreaView style={styles.hud} pointerEvents="box-none">
        {/* Top bar: the coach's voice on the left, shooting modes on the right. */}
        <View style={styles.topBar}>
          {voice.canSpeak ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Change coach voice"
              onPress={voice.next}
              style={styles.chip}>
              <SymbolView
                name={{
                  ios: voice.persona ? 'speaker.wave.2.fill' : 'speaker.slash.fill',
                  android: voice.persona ? 'volume_up' : 'volume_off',
                  web: voice.persona ? 'volume_up' : 'volume_off',
                }}
                size={15}
                tintColor="#FFFFFF"
              />
              <Text style={styles.chipText}>
                {voice.persona ? voice.persona.name : 'Voice off'}
              </Text>
            </Pressable>
          ) : (
            <View />
          )}
          <View style={styles.modes}>
            <Pressable
              accessibilityRole="switch"
              accessibilityLabel="Take the photo automatically when it's perfect"
              accessibilityState={{ checked: auto }}
              onPress={() => setAuto((a) => !a)}
              style={[styles.chip, auto && styles.chipOn]}>
              <SymbolView
                name={{ ios: 'sparkles', android: 'auto_awesome', web: 'auto_awesome' }}
                size={15}
                tintColor="#FFFFFF"
              />
              <Text style={styles.chipText}>Auto</Text>
            </Pressable>
            <Pressable
              accessibilityRole="switch"
              accessibilityLabel={`Burst: take ${BURST_SIZE} and keep the best`}
              accessibilityState={{ checked: burstMode }}
              onPress={() => setBurstMode((b) => !b)}
              style={[styles.chip, burstMode && styles.chipOn]}>
              <SymbolView
                name={{
                  ios: 'square.stack.3d.down.right',
                  android: 'burst_mode',
                  web: 'burst_mode',
                }}
                size={15}
                tintColor="#FFFFFF"
              />
              <Text style={styles.chipText}>Burst</Text>
            </Pressable>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Find your best angles"
              onPress={() => router.push('/angles')}
              style={styles.iconButton}>
              <SymbolView
                name={{ ios: 'viewfinder', android: 'center_focus_weak', web: 'center_focus_weak' }}
                size={18}
                tintColor="#FFFFFF"
              />
            </Pressable>
          </View>
        </View>

        {/* The coach's tip, with a dot for what kind it is, and the live numbers under it. */}
        <View style={styles.tipArea} pointerEvents="none">
          {(tip || analysis) && (
            <View style={styles.tip}>
              <View
                style={[
                  styles.tipDot,
                  error || redFlag ? styles.dotProblem : tip ? styles.dotCoach : styles.dotGood,
                ]}
              />
              <Text style={styles.tipText}>{tip ?? 'Looks good'}</Text>
            </View>
          )}
          {notice ? (
            <View style={styles.tip}>
              <View style={[styles.tipDot, styles.dotGood]} />
              <Text style={styles.tipText}>{notice}</Text>
            </View>
          ) : (
            auto &&
            analysis?.shot?.perfect &&
            !capturing && (
              <View style={styles.tip}>
                <View style={[styles.tipDot, styles.dotGood]} />
                <Text style={styles.tipText}>Perfect: hold still…</Text>
              </View>
            )
          )}
          {analysis && !error && (
            <Text style={styles.stats}>
              {analysis.faces.length} face{analysis.faces.length === 1 ? '' : 's'} ·{' '}
              {fps.toFixed(1)} fps · {analysis.ms} ms
              {analysis.shot?.scored_by === 'model'
                ? ` · style match ${Math.round(analysis.shot.score * 100)}%`
                : ''}
            </Text>
          )}
        </View>

        {/* Bottom: lenses above the shutter, then last photo · shutter · flip, like the iPhone. */}
        <View style={styles.bottom}>
          <View style={styles.zoomRow}>
            {facing === 'back' && ultraWideLens && (
              <View style={styles.zoom}>
                {(
                  [
                    ['0.5', true],
                    ['1×', false],
                  ] as const
                ).map(([label, wide]) => (
                  <Pressable
                    key={label}
                    accessibilityRole="button"
                    accessibilityState={{ selected: ultraWide === wide }}
                    onPress={() => setUltraWide(wide)}
                    hitSlop={6}
                    style={[styles.zoomOption, ultraWide === wide && styles.zoomSelected]}>
                    <Text style={[styles.zoomText, ultraWide === wide && styles.zoomTextSelected]}>
                      {label}
                    </Text>
                  </Pressable>
                ))}
              </View>
            )}
          </View>

          <View style={styles.controls}>
            <View style={styles.side}>
              {/* The way to the gallery: the last photo, or a gallery button before there is one. */}
              {photos[0] ? (
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel="Open the photo gallery"
                  onPress={() => router.push('/photos')}>
                  <Image source={{ uri: photos[0].uri }} style={styles.thumb} />
                  <View style={styles.badge}>
                    <Text style={styles.badgeText}>{photos.length}</Text>
                  </View>
                </Pressable>
              ) : (
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel="Open the photo gallery"
                  onPress={() => router.push('/photos')}
                  style={styles.roundButton}>
                  <SymbolView
                    name={{
                      ios: 'photo.on.rectangle',
                      android: 'photo_library',
                      web: 'photo_library',
                    }}
                    size={20}
                    tintColor="#FFFFFF"
                  />
                </Pressable>
              )}
            </View>

            <Pressable
              accessibilityRole="button"
              accessibilityLabel={burstMode ? `Take ${BURST_SIZE} and keep the best` : 'Take photo'}
              disabled={capturing}
              onPress={takePhoto}
              style={styles.shutter}>
              {({ pressed }) => (
                <View
                  style={[
                    styles.shutterInner,
                    burstMode && styles.shutterBurst,
                    (pressed || capturing) && styles.shutterPressed,
                  ]}
                />
              )}
            </Pressable>

            <View style={styles.side}>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={
                  facing === 'back' ? 'Switch to the front camera' : 'Switch to the back camera'
                }
                onPress={flip}
                style={styles.roundButton}>
                <SymbolView
                  name={{
                    ios: 'arrow.triangle.2.circlepath',
                    android: 'flip_camera_ios',
                    web: 'flip_camera_ios',
                  }}
                  size={22}
                  tintColor="#FFFFFF"
                />
              </Pressable>
            </View>
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
    fontFamily: FontFamily.body,
    color: '#fff',
    fontSize: 17,
    textAlign: 'center',
  },
  hud: {
    flex: 1,
    paddingBottom: Spacing.four,
  },
  topBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 26,
    paddingTop: 8,
  },
  modes: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    height: 36,
    paddingHorizontal: 12,
    borderRadius: 18,
    backgroundColor: 'rgba(0,0,0,0.45)',
  },
  chipOn: {
    backgroundColor: ACCENT,
  },
  chipText: {
    fontFamily: FontFamily.bodyBold,
    color: '#FFFFFF',
    fontSize: 14,
  },
  iconButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(0,0,0,0.45)',
  },
  tipArea: {
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 26,
    paddingTop: 14,
  },
  tip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    maxWidth: '100%',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 18,
    backgroundColor: 'rgba(20,20,20,0.72)',
  },
  tipDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  dotCoach: {
    backgroundColor: ACCENT,
  },
  dotGood: {
    backgroundColor: '#3DDC84',
  },
  dotProblem: {
    backgroundColor: '#F87171',
  },
  tipText: {
    flexShrink: 1,
    fontFamily: FontFamily.bodyBold,
    color: '#FFFFFF',
    fontSize: 17,
    lineHeight: 22,
  },
  stats: {
    fontFamily: FontFamily.body,
    color: 'rgba(255,255,255,0.75)',
    fontSize: 12,
    fontVariant: ['tabular-nums'],
  },
  bottom: {
    marginTop: 'auto',
    gap: 14,
  },
  zoomRow: {
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
  },
  zoom: {
    flexDirection: 'row',
    gap: 4,
    padding: 3,
    borderRadius: 999,
    backgroundColor: 'rgba(0,0,0,0.45)',
  },
  zoomOption: {
    minWidth: 34,
    height: 30,
    paddingHorizontal: 6,
    borderRadius: 15,
    alignItems: 'center',
    justifyContent: 'center',
  },
  zoomSelected: {
    backgroundColor: 'rgba(255,255,255,0.9)',
  },
  zoomText: {
    fontFamily: FontFamily.bodyBold,
    color: '#FFFFFF',
    fontSize: 13,
  },
  zoomTextSelected: {
    color: INK,
  },
  controls: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 38,
  },
  side: {
    flex: 1,
    alignItems: 'center',
  },
  shutter: {
    width: 80,
    height: 80,
    borderRadius: 40,
    borderWidth: 4,
    borderColor: '#FFFFFF',
    alignItems: 'center',
    justifyContent: 'center',
  },
  shutterInner: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: '#FFFFFF',
  },
  // Burst on: the shutter's centre in the brand colour, so the mode is visible where you press.
  shutterBurst: {
    backgroundColor: ACCENT,
  },
  shutterPressed: {
    transform: [{ scale: 0.9 }],
    opacity: 0.8,
  },
  roundButton: {
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(0,0,0,0.45)',
  },
  thumb: {
    width: 48,
    height: 48,
    borderRadius: 10,
    borderWidth: 2,
    borderColor: '#FFFFFF',
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
    backgroundColor: ACCENT,
  },
  badgeText: {
    fontFamily: FontFamily.bodyBold,
    color: '#FFFFFF',
    fontSize: 12,
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
    fontFamily: FontFamily.bodyBold,
    color: '#fff',
  },
});
