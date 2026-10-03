import { CameraView, useCameraPermissions, type CameraType } from 'expo-camera';
import { Image } from 'expo-image';
import { router, useIsFocused } from 'expo-router';
import { useRef, useState } from 'react';
import { Alert, Animated, Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { FaceOverlay } from '@/components/face-overlay';
import { usePhotos } from '@/components/photos-provider';
import { BottomTabInset, Spacing } from '@/constants/theme';
import { useFrameAnalysis } from '@/hooks/use-frame-analysis';
import { SERVER_URL } from '@/lib/server';

const WIDE_LENS = 'builtInWideAngleCamera';

export default function CameraScreen() {
  const [permission, requestPermission] = useCameraPermissions();
  const isFocused = useIsFocused();
  const cameraRef = useRef<CameraView>(null);
  const { photos, add } = usePhotos();

  const [ready, setReady] = useState(false);
  const [facing, setFacing] = useState<CameraType>('back');
  const [lenses, setLenses] = useState<string[]>([]);
  const [ultraWide, setUltraWide] = useState(false);
  const [layout, setLayout] = useState({ width: 0, height: 0 });
  const [capturing, setCapturing] = useState(false);
  const [flash] = useState(() => new Animated.Value(0));

  const { analysis, error, fps, capture } = useFrameAnalysis(cameraRef, ready && isFocused);

  // iOS reports lens names like "Back Ultra Wide Camera"; only the back camera has one.
  const ultraWideLens = lenses.find((l) => /ultra\s*wide/i.test(l));
  const selectedLens = facing === 'back' && ultraWide && ultraWideLens ? ultraWideLens : WIDE_LENS;

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

  async function takePhoto() {
    if (capturing) return;
    setCapturing(true);
    // Remember what the coach saw at the moment of the press, not after the capture delay.
    const seen = analysis;
    flash.setValue(1);
    Animated.timing(flash, { toValue: 0, duration: 250, useNativeDriver: true }).start();
    try {
      const photo = await capture();
      if (photo) add(photo.uri, seen);
    } catch (e) {
      Alert.alert('Photo failed', e instanceof Error ? e.message : String(e));
    } finally {
      setCapturing(false);
    }
  }

  function flip() {
    setReady(false);
    setFacing((f) => (f === 'back' ? 'front' : 'back'));
  }

  const tip = error ? `Can't reach ${SERVER_URL}` : analysis?.warnings[0]?.message;

  return (
    <View
      style={styles.fill}
      onLayout={(e) => setLayout(e.nativeEvent.layout)}>
      {isFocused && (
        <CameraView
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
          {analysis && !error && (
            <Text style={styles.stats}>
              {analysis.faces.length} face{analysis.faces.length === 1 ? '' : 's'} · {fps.toFixed(1)} fps ·{' '}
              {analysis.ms} ms
            </Text>
          )}
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
