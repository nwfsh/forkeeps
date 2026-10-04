import { router, Stack, usePathname } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useOnboarding } from '@/components/onboarding-provider';
import type { RetrainResult } from '@/lib/server';
import { FontFamily } from '@/constants/theme';

// The pages in order, for the preview's Skip button.
const PAGES = [
  '/onboarding',
  '/onboarding/how-it-works',
  '/onboarding/profile',
  '/onboarding/camera-access',
  '/onboarding/record',
  '/onboarding/compare',
  '/onboarding/results',
  '/onboarding/voice',
  '/onboarding/makeup',
] as const;

// Made-up results so the profile page has something to show when skipped to.
const PREVIEW_RESULTS: RetrainResult = {
  reviewed: 20,
  confidence: 1,
  priorities: [
    { feature: 'chin_up', prefers: 'Chin down', share: 0.48, weight: -1.5 },
    { feature: 'chin_up_curve', prefers: '', share: 0.17, weight: 0.5 },
    { feature: 'smile', prefers: '', share: 0.11, weight: -0.3 },
    { feature: 'left_side', prefers: '', share: 0.08, weight: 0.25 },
    { feature: 'left_side_curve', prefers: '', share: 0.06, weight: 0.2 },
    { feature: 'teeth_shown', prefers: '', share: 0.06, weight: -0.18 },
    { feature: 'eye_contact', prefers: '', share: 0.05, weight: -0.15 },
  ],
};

export default function OnboardingLayout() {
  const { preview, results, setResults, finish } = useOnboarding();
  const pathname = usePathname();
  const insets = useSafeAreaInsets();

  function skip() {
    const next = PAGES[PAGES.indexOf(pathname as (typeof PAGES)[number]) + 1];
    if (!next) return finish();
    if (next === '/onboarding/results' && !results) setResults(PREVIEW_RESULTS);
    router.push(next);
  }

  return (
    <View style={styles.fill}>
      <Stack screenOptions={{ headerShown: false }} />
      {preview && (
        <View style={[styles.skipRow, { top: insets.top + 4 }]} pointerEvents="box-none">
          <Pressable accessibilityRole="button" onPress={skip} hitSlop={8} style={styles.skip}>
            <Text style={styles.skipText}>
              {pathname === PAGES[PAGES.length - 1] ? 'Done ›' : 'Skip ›'}
            </Text>
          </Pressable>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  fill: {
    flex: 1,
  },
  skipRow: {
    position: 'absolute',
    left: 0,
    right: 0,
    alignItems: 'center',
  },
  skip: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 999,
    backgroundColor: 'rgba(26,26,26,0.75)',
  },
  skipText: {
    fontFamily: FontFamily.bodyBold,
    color: '#FFFFFF',
    fontSize: 13,
  },
});
