import { useCameraPermissions } from 'expo-camera';
import { Image } from 'expo-image';
import { router } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useOnboarding } from '@/components/onboarding-provider';
import {
  GradientBackground,
  INK,
  MUTED,
  PillButton,
  StepDots,
  Appear,
} from '@/components/onboarding-style';
import { FontFamily } from '@/constants/theme';

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
        {/* Filming is step 2 of 3 (name, film, compare); this page leads into it. */}
        <View style={styles.steps}>
          <StepDots step={2} steps={3} />
        </View>
      </View>

      <View style={styles.hero}>
        <Appear kind="drop" order={1} style={styles.icon}>
          {/* A group posing together: a line drawing straight on the gradient. */}
          <Image
            source={require('@/assets/images/onboarding/group-pose.svg')}
            style={styles.illustration}
            contentFit="contain"
            accessibilityLabel="Friends posing for a photo"
          />
        </Appear>
        <View style={styles.copy}>
          <Text style={styles.title}>Pose for us so we know what you like</Text>
          <Text style={styles.subtitle}>
            Next you’ll film a few seconds of yourself, and later the coach watches the preview to
            give you tips. The camera is only on while you’re recording or on the camera screen.
          </Text>
        </View>
      </View>

      <View style={[styles.footer, { marginBottom: insets.bottom + 10 }]}>
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
    paddingHorizontal: 34,
  },
  steps: {
    marginTop: 16,
  },
  back: {
    fontFamily: FontFamily.bodyBold,
    color: INK,
    fontSize: 16,
  },
  hero: {
    position: 'absolute',
    top: HERO_TOP,
    // A little below the 24% mark.
    marginTop: 30,
    left: 42,
    right: 42,
    alignItems: 'center',
    gap: 12,
  },
  icon: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  // The line drawing (a vector, 853 x 720) on its own on the gradient, small, just above the title.
  illustration: {
    width: 150,
    height: 150 / (853 / 720),
  },
  copy: {
    alignItems: 'center',
    gap: 16,
  },
  title: {
    fontFamily: FontFamily.heading,
    color: INK,
    fontSize: 34,
    lineHeight: 43,
    letterSpacing: -0.6,
    textAlign: 'center',
  },
  subtitle: {
    fontFamily: FontFamily.body,
    color: MUTED,
    fontSize: 17,
    lineHeight: 24,
    textAlign: 'center',
  },
  footer: {
    position: 'absolute',
    bottom: FOOTER_BOTTOM,
    left: 30,
    right: 30,
    alignItems: 'center',
    gap: 16,
  },
  notNow: {
    fontFamily: FontFamily.bodyBold,
    color: MUTED,
    fontSize: 16,
  },
});
