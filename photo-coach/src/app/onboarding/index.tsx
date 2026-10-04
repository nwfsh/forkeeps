import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import {
  BackLink,
  GradientBackground,
  INK,
  MUTED,
  PillButton,
} from '@/components/onboarding-style';
import { DrawnRibbon } from '@/components/drawn-ribbon';
import { useOnboarding } from '@/components/onboarding-provider';
import { FontFamily } from '@/constants/theme';

// The ribbon's size: its own width in the SVG, scaled up.
const RIBBON_WIDTH = 122 * 1.4;
// The button block's distance from the bottom, above the home indicator.
const FOOTER_BOTTOM = 50;

export default function WelcomeScreen() {
  const insets = useSafeAreaInsets();
  const { replaying, finish } = useOnboarding();
  // Counts each time this page comes into view, including coming Back to it; the logo and
  // background are keyed on it, so their animations play again from the start every time.
  const [visit, setVisit] = useState(0);
  useFocusEffect(useCallback(() => setVisit((v) => v + 1), []));

  return (
    <View
      style={[
        styles.screen,
        { paddingTop: insets.top, paddingBottom: insets.bottom + FOOTER_BOTTOM },
      ]}>
      <GradientBackground key={`background-${visit}`} moving />
      {/* Opened again from the gallery: the way back without redoing onboarding. */}
      {replaying && (
        <View style={styles.topBar}>
          <BackLink label="‹ Back to camera" onPress={finish} />
        </View>
      )}

      {/* The logo and words as one group, centred on the screen (behind the controls, so the
          button and Back don't push it off-centre). */}
      <View style={styles.middle} pointerEvents="none">
        {/* The logo draws itself in: its one animation on this page. */}
        <DrawnRibbon key={`logo-${visit}`} width={RIBBON_WIDTH} />
        <View style={styles.copy}>
          <Text style={styles.title}>{'Get the shot\non the first try'}</Text>
          <Text style={styles.subtitle}>
            Teach the app what you like in photos of yourself. It coaches you before the shutter.
          </Text>
        </View>
      </View>

      <View style={styles.footer}>
        <PillButton label="Get started" onPress={() => router.push('/onboarding/how-it-works')} />
        <View style={styles.hint}>
          <Text style={styles.hintLabel}>Takes about 2 minutes</Text>
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
  topBar: {
    paddingHorizontal: 34,
    paddingTop: 8,
  },
  middle: {
    ...StyleSheet.absoluteFill,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 32,
  },
  copy: {
    alignItems: 'center',
    gap: 14,
    paddingHorizontal: 42,
  },
  title: {
    fontFamily: FontFamily.heading,
    color: INK,
    fontSize: 36,
    lineHeight: 45,
    letterSpacing: -0.8,
    textAlign: 'center',
  },
  subtitle: {
    fontFamily: FontFamily.body,
    maxWidth: 300,
    color: MUTED,
    fontSize: 17,
    lineHeight: 25,
    textAlign: 'center',
  },
  footer: {
    marginTop: 'auto',
    paddingHorizontal: 30,
    alignItems: 'center',
    gap: 16,
  },
  hint: {
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: 999,
    backgroundColor: '#FFFFFF',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#E5E5EA',
    shadowColor: '#000000',
    shadowOpacity: 0.06,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 2,
  },
  hintLabel: {
    fontFamily: FontFamily.body,
    color: MUTED,
    fontSize: 14,
  },
});
