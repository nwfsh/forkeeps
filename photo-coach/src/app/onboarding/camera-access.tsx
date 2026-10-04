import { useCameraPermissions } from 'expo-camera';
import { router } from 'expo-router';
import { SymbolView } from 'expo-symbols';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useOnboarding } from '@/components/onboarding-provider';
import { GradientBackground, INK, MUTED, PillButton } from '@/components/onboarding-style';

// Where things sit, as a share of the screen height, like the welcome screen.
const HERO_TOP = '24%';
const FOOTER_BOTTOM = '8%';

/**
 * Explains the camera before iOS/Android ask, so the system prompt isn't a surprise. With
 * access, onboarding goes on to recording; without it, "Not now" skips straight to the camera
 * tabs (see app/_layout.tsx), which have their own "Allow camera" button.
 */
export default function CameraAccessScreen() {
  const [permission, requestPermission] = useCameraPermissions();
  const { finish } = useOnboarding();
  const insets = useSafeAreaInsets();

  async function allow() {
    const result = await requestPermission();
    // Recording needs the camera; without it there's nothing to learn from yet.
    if (result.granted) router.push('/onboarding/record');
    else finish();
  }

  return (
    <View style={styles.screen}>
      <GradientBackground />

      <View style={[styles.topBar, { paddingTop: insets.top + 8 }]}>
        <Pressable accessibilityRole="button" onPress={() => router.back()} hitSlop={12}>
          <Text style={styles.back}>Back</Text>
        </Pressable>
      </View>

      <View style={styles.hero}>
        <View style={styles.icon}>
          <SymbolView
            name={{ ios: 'camera', android: 'photo_camera', web: 'photo_camera' }}
            size={40}
            tintColor={INK}
          />
        </View>
        <View style={styles.copy}>
          <Text style={styles.title}>Pose for us so we know what you like</Text>
          <Text style={styles.subtitle}>
            Next you’ll film a few seconds of yourself, and later the coach watches the preview to
            give you tips. The camera is only on while you’re recording or on the camera screen.
          </Text>
        </View>
      </View>

      <View style={[styles.footer, { marginBottom: insets.bottom }]}>
        {permission?.granted ? (
          <PillButton label="Continue" onPress={() => router.push('/onboarding/record')} />
        ) : (
          <>
            <PillButton label="Allow camera" onPress={allow} />
            <Pressable accessibilityRole="button" onPress={finish} hitSlop={8}>
              <Text style={styles.notNow}>Not now</Text>
            </Pressable>
          </>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: '#FFFFFF',
  },
  topBar: {
    paddingHorizontal: 24,
  },
  back: {
    color: INK,
    fontSize: 16,
    fontWeight: '600',
  },
  hero: {
    position: 'absolute',
    top: HERO_TOP,
    left: 32,
    right: 32,
    alignItems: 'center',
    gap: 32,
  },
  icon: {
    width: 96,
    height: 96,
    borderRadius: 48,
    backgroundColor: '#FFFFFF',
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000000',
    shadowOpacity: 0.08,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 8 },
    elevation: 3,
  },
  copy: {
    alignItems: 'center',
    gap: 16,
  },
  title: {
    color: INK,
    fontSize: 34,
    lineHeight: 40,
    fontWeight: '700',
    letterSpacing: -0.6,
    textAlign: 'center',
  },
  subtitle: {
    color: MUTED,
    fontSize: 17,
    lineHeight: 24,
    textAlign: 'center',
  },
  footer: {
    position: 'absolute',
    bottom: FOOTER_BOTTOM,
    left: 20,
    right: 20,
    alignItems: 'center',
    gap: 16,
  },
  notNow: {
    color: MUTED,
    fontSize: 16,
    fontWeight: '600',
  },
});
