import { Image } from 'expo-image';
import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, useWindowDimensions, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { GradientBackground, PillButton, ACCENT, Appear, INK } from '@/components/onboarding-style';
import { FontFamily } from '@/constants/theme';

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
// The wordmark header's width, and the button's distance from the bottom (above the home bar).
const WORDMARK_WIDTH = 110;
// The full-colour PickTure wordmark from the design (pink ribbon letters), and its shape.
const WORDMARK = require('@/assets/images/onboarding/wordmark-color.png');
const WORDMARK_RATIO = 282 / 120;
const FOOTER_BOTTOM = 82;
// The least space between the header and the steps, and how far below the screen's middle the
// steps are centred.
const STEPS_GAP = 24;
const STEPS_DROP = 20;

export default function HowItWorksScreen() {
  const insets = useSafeAreaInsets();
  const { height } = useWindowDimensions();
  // The steps are centred on the screen, but never closer than STEPS_GAP below the header; both
  // are measured once laid out (until then the steps sit in the space below the header).
  const [headerBottom, setHeaderBottom] = useState<number | null>(null);
  const [stepsHeight, setStepsHeight] = useState<number | null>(null);
  const stepsTop =
    headerBottom === null || stepsHeight === null
      ? null
      : Math.max((height - stepsHeight) / 2 + STEPS_DROP, headerBottom + STEPS_GAP);

  return (
    <View
      style={[
        styles.screen,
        { paddingTop: insets.top + 8, paddingBottom: insets.bottom + FOOTER_BOTTOM },
      ]}>
      <GradientBackground kind="multicolor" />

      <Appear kind="drop" order={0} style={styles.topBar}>
        <Pressable accessibilityRole="button" onPress={() => router.back()} hitSlop={12}>
          <Text style={styles.back}>Back</Text>
        </Pressable>
        {/* The full-colour PickTure logo in the top-right corner. */}
        <Image
          source={WORDMARK}
          style={{ width: WORDMARK_WIDTH, height: WORDMARK_WIDTH / WORDMARK_RATIO }}
          contentFit="contain"
          accessibilityLabel="PickTure"
        />
      </Appear>

      {/* The page title, centred. */}
      <Appear
        kind="drop"
        order={1}
        style={styles.header}
        onLayout={(e) => setHeaderBottom(e.nativeEvent.layout.y + e.nativeEvent.layout.height)}>
        <Text style={styles.title}>How It Works</Text>
      </Appear>

      {/* The steps, left-aligned in a column, centred on the screen where there's room. */}
      <View style={[styles.copy, stepsTop !== null && { ...styles.centred, top: stepsTop }]}>
        <View style={styles.steps} onLayout={(e) => setStepsHeight(e.nativeEvent.layout.height)}>
          {STEPS.map((step, i) => (
            // The instructions glide in one after another, each starting partway in.
            <Appear key={step.title} kind="glide" order={3 + 2 * i} style={styles.step}>
              <Text style={styles.number}>{i + 1}</Text>
              <View style={styles.stepText}>
                <Text style={styles.stepTitle}>{step.title}</Text>
                <Text style={styles.stepBody}>{step.body}</Text>
              </View>
            </Appear>
          ))}
        </View>
      </View>

      <Appear order={9} style={styles.footer}>
        <PillButton label="Let's go" onPress={() => router.push('/onboarding/profile')} />
      </Appear>
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
    minHeight: 32,
    paddingHorizontal: 34,
  },
  header: {
    alignItems: 'center',
    gap: 20,
    marginTop: 126,
  },
  back: {
    fontFamily: FontFamily.bodyBold,
    color: INK,
    fontSize: 16,
  },
  copy: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: 42,
  },
  centred: {
    position: 'absolute',
    left: 0,
    right: 0,
    flex: undefined,
  },
  title: {
    fontFamily: FontFamily.heading,
    color: INK,
    fontSize: 34,
    lineHeight: 43,
    letterSpacing: -0.6,
    textAlign: 'center',
  },
  steps: {
    gap: 28,
  },
  step: {
    flexDirection: 'row',
    gap: 18,
    alignItems: 'center',
  },
  // A big number in the brand colour beside each step, in a fixed-width column so the step text
  // lines up.
  number: {
    width: 44,
    fontFamily: FontFamily.headingBlack,
    fontSize: 60,
    lineHeight: 75,
    color: ACCENT,
    textAlign: 'center',
  },
  stepText: {
    flex: 1,
    gap: 4,
  },
  stepTitle: {
    fontFamily: FontFamily.heading,
    color: INK,
    fontSize: 18,
  },
  stepBody: {
    fontFamily: FontFamily.body,
    // The same dark pink as the step numbers.
    color: ACCENT,
    fontSize: 16,
    lineHeight: 22,
  },
  footer: {
    marginTop: 'auto',
    paddingHorizontal: 30,
  },
});
