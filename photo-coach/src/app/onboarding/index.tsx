import { router } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { GradientBackground, INK, MUTED, PillButton, Ribbon } from '@/components/onboarding-style';

// The ribbon's own width in the SVG, a touch larger, as in the design.
const RIBBON_WIDTH = 122 * 1.05;
// Where things sit, as a share of the screen height, measured from the design.
const RIBBON_TOP = '30%';
const TEXT_TOP = '56%';
const FOOTER_BOTTOM = '8%';

export default function WelcomeScreen() {
  const insets = useSafeAreaInsets();

  return (
    <View style={styles.screen}>
      <GradientBackground />

      <View style={styles.hero}>
        <Ribbon width={RIBBON_WIDTH} />
      </View>

      <View style={styles.copy}>
        <Text style={styles.title}>Get the shot on the first try</Text>
        <Text style={styles.subtitle}>
          Teach the app what you like in photos of yourself. It coaches you before the shutter.
        </Text>
      </View>

      <View style={[styles.footer, { marginBottom: insets.bottom }]}>
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
  hero: {
    position: 'absolute',
    top: RIBBON_TOP,
    left: 0,
    right: 0,
    alignItems: 'center',
  },
  copy: {
    position: 'absolute',
    top: TEXT_TOP,
    left: 32,
    right: 32,
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
    color: MUTED,
    fontSize: 14,
  },
});
