import { router } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import {
  GradientBackground,
  INK,
  MUTED,
  PillButton,
  Wordmark,
} from '@/components/onboarding-style';

const STEPS = [
  { title: 'Film yourself', body: 'Fifteen seconds, however you like.' },
  {
    title: 'Pick your favourites',
    body: 'We show you two moments at a time. Tap the one you like more.',
  },
  {
    title: 'Get coached live',
    body: 'We learn what you like and nudge you toward it, out loud, as you shoot.',
  },
];
// Where the copy starts and the button sits, as a share of the screen height, matching the
// welcome screen so the two read as one sequence.
const TEXT_TOP = '30%';
const FOOTER_BOTTOM = '8%';

export default function HowItWorksScreen() {
  const insets = useSafeAreaInsets();

  return (
    <View style={styles.screen}>
      <GradientBackground kind="multicolor" />

      <View style={[styles.topBar, { paddingTop: insets.top + 8 }]}>
        <Wordmark width={150} />
        <Pressable accessibilityRole="button" onPress={() => router.back()} hitSlop={12}>
          <Text style={styles.back}>Back</Text>
        </Pressable>
      </View>

      <View style={styles.copy}>
        <Text style={styles.title}>How it works</Text>
        <View style={styles.steps}>
          {STEPS.map((step, i) => (
            <View key={step.title} style={styles.step}>
              <View style={styles.number}>
                <Text style={styles.numberText}>{i + 1}</Text>
              </View>
              <View style={styles.stepText}>
                <Text style={styles.stepTitle}>{step.title}</Text>
                <Text style={styles.stepBody}>{step.body}</Text>
              </View>
            </View>
          ))}
        </View>
      </View>

      <View style={[styles.footer, { marginBottom: insets.bottom }]}>
        <PillButton label="Let's go" onPress={() => router.push('/onboarding/profile')} />
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
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 24,
  },
  back: {
    color: INK,
    fontSize: 16,
    fontWeight: '600',
  },
  copy: {
    position: 'absolute',
    top: TEXT_TOP,
    left: 28,
    right: 28,
    gap: 28,
  },
  title: {
    color: INK,
    fontSize: 34,
    lineHeight: 40,
    fontWeight: '700',
    letterSpacing: -0.6,
  },
  steps: {
    gap: 24,
  },
  step: {
    flexDirection: 'row',
    gap: 16,
    alignItems: 'flex-start',
  },
  number: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: '#1B1B1B',
    alignItems: 'center',
    justifyContent: 'center',
  },
  numberText: {
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '700',
  },
  stepText: {
    flex: 1,
    gap: 4,
  },
  stepTitle: {
    color: INK,
    fontSize: 18,
    fontWeight: '600',
  },
  stepBody: {
    color: MUTED,
    fontSize: 16,
    lineHeight: 22,
  },
  footer: {
    position: 'absolute',
    bottom: FOOTER_BOTTOM,
    left: 20,
    right: 20,
  },
});
