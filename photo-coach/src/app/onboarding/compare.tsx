import { router } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { useOnboarding } from '@/components/onboarding-provider';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/placeholders/button';
import { PhotoCard } from '@/components/placeholders/photo-card';
import { ProgressBar } from '@/components/placeholders/progress-bar';
import { Screen } from '@/components/placeholders/screen';
import { Spacing } from '@/constants/theme';
import { MOCK_PAIRS } from '@/lib/onboarding';

/**
 * "Choose between pics". With mock data, one round is every mock pair; the real version
 * keeps going until the server's ranker says it has learned enough (15–40 picks).
 */
export default function CompareScreen() {
  const { pick } = useOnboarding();
  // Pairs shown so far, picked or skipped. Coming back from results starts a new round.
  const [shown, setShown] = useState(0);
  const round = MOCK_PAIRS.length;
  const done = shown % round;
  const [a, b] = MOCK_PAIRS[done];

  function next() {
    setShown((n) => n + 1);
    if (done + 1 === round) router.push('/onboarding/results');
  }

  function choose(winner: string, loser: string) {
    pick(winner, loser);
    next();
  }

  return (
    <Screen
      back
      topRight={<Button variant="text" label="Skip" onPress={() => router.push('/onboarding/camera-access')} />}
      footer={<Button variant="secondary" label="Can't decide" onPress={next} />}>
      <ProgressBar progress={done / round} label={`${done} of ${round}`} />
      <View style={styles.heading}>
        <ThemedText type="subtitle">Which do you like more?</ThemedText>
        <ThemedText themeColor="textSecondary">Go with your gut. There are no wrong answers.</ThemedText>
      </View>
      <View style={styles.pair}>
        <PhotoCard photo={a} onPress={() => choose(a.id, b.id)} />
        <PhotoCard photo={b} onPress={() => choose(b.id, a.id)} />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  heading: {
    gap: Spacing.two,
  },
  pair: {
    flexDirection: 'row',
    gap: Spacing.three,
  },
});
