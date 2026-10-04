import { router } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/placeholders/button';
import { Illustration } from '@/components/placeholders/illustration';
import { Screen } from '@/components/placeholders/screen';
import { StepRow } from '@/components/placeholders/step-row';
import { Spacing } from '@/constants/theme';

const STEPS = [
  { title: 'Pick your favourites', body: "We'll show you two photos at a time. Tap the one you like more." },
  { title: 'We learn your style', body: 'Smile, angle, framing: we work out what matters most to you.' },
  { title: 'Get coached live', body: "Point the camera and we'll nudge you toward shots you'll love." },
];

export default function HowItWorksScreen() {
  return (
    <Screen back footer={<Button label="Start picking" onPress={() => router.push('/onboarding/compare')} />}>
      <Illustration name="how it works" height={180} />
      <ThemedText type="subtitle">How it works</ThemedText>
      <View style={styles.steps}>
        {STEPS.map((step, i) => (
          <StepRow key={step.title} number={i + 1} title={step.title} body={step.body} />
        ))}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  steps: {
    gap: Spacing.four,
  },
});
