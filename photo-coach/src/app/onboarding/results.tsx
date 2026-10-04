import { router } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Badge } from '@/components/placeholders/badge';
import { Button } from '@/components/placeholders/button';
import { PriorityRow } from '@/components/placeholders/priority-row';
import { Screen } from '@/components/placeholders/screen';
import { Spacing } from '@/constants/theme';
import { MOCK_RESULTS, type Confidence } from '@/lib/onboarding';

// How many priorities to show; the rest are noise this early.
const SHOWN = 3;

const CONFIDENCE_TEXT: Record<Confidence, { badge: string; body: string }> = {
  clear: { badge: 'Clear pattern', body: 'Your picks point clearly to what you like.' },
  likely: { badge: 'Likely pattern', body: 'A few more picks would firm this up.' },
  unclear: {
    badge: 'No clear pattern yet',
    body: 'Your picks may depend on things we can’t measure yet, like lighting or outfit.',
  },
};

export default function ResultsScreen() {
  // TODO: fetch the real results for this user's picks.
  const { priorities, confidence } = MOCK_RESULTS;
  const shown = priorities.slice(0, SHOWN);
  const largest = Math.max(...shown.map((p) => p.share));

  return (
    <Screen
      footer={
        <>
          <Button label="Start shooting" onPress={() => router.push('/onboarding/camera-access')} />
          <Button variant="text" label="Keep picking" onPress={() => router.back()} />
        </>
      }>
      <View style={styles.heading}>
        <ThemedText type="subtitle">Your photo style</ThemedText>
        <Badge label={CONFIDENCE_TEXT[confidence].badge} />
        <ThemedText themeColor="textSecondary">{CONFIDENCE_TEXT[confidence].body}</ThemedText>
      </View>
      <View style={styles.list}>
        <ThemedText style={styles.listTitle}>You tend to pick photos with…</ThemedText>
        {shown.map((priority) => (
          <PriorityRow key={priority.feature} priority={priority} largestShare={largest} />
        ))}
      </View>
      <ThemedText type="small" themeColor="textSecondary">
        The coach will focus on these when it gives you tips.
      </ThemedText>
    </Screen>
  );
}

const styles = StyleSheet.create({
  heading: {
    gap: Spacing.two,
  },
  list: {
    gap: Spacing.three,
  },
  listTitle: {
    fontWeight: 600,
  },
});
