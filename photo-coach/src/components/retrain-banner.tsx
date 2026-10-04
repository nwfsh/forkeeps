import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing } from '@/constants/theme';
import { fetchModelStatus, retrainModel, type ModelStatus, type RetrainResult } from '@/lib/server';

// How many of the new model's priorities to spell out.
const SHOWN = 3;

/**
 * Offers to retrain the coach once enough photos have been kept or removed since it last
 * learned (the server decides how many). Shows nothing until then, or if the server is away.
 */
export function RetrainBanner() {
  const [status, setStatus] = useState<ModelStatus | null>(null);
  const [result, setResult] = useState<RetrainResult | null>(null);
  const [training, setTraining] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Checked whenever the screen comes back into view, e.g. after a round of review.
  useFocusEffect(
    useCallback(() => {
      fetchModelStatus()
        .then(setStatus)
        .catch(() => setStatus(null));
    }, [])
  );

  async function retrain() {
    setTraining(true);
    setError(null);
    try {
      const trained = await retrainModel();
      setResult(trained);
      setStatus(await fetchModelStatus());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setTraining(false);
    }
  }

  if (result) {
    return (
      <ThemedView type="backgroundElement" style={styles.banner}>
        <ThemedText type="smallBold">
          Coach retrained on {result.reviewed} photos · {Math.round(result.confidence * 100)}% sure
        </ThemedText>
        {result.priorities.slice(0, SHOWN).map((p) => (
          <ThemedText key={p.feature} type="small" themeColor="textSecondary">
            • {p.prefers} ({Math.round(p.share * 100)}%)
          </ThemedText>
        ))}
        <Pressable onPress={() => setResult(null)} hitSlop={8}>
          <ThemedText type="small" themeColor="textSecondary" style={styles.dismiss}>
            Dismiss
          </ThemedText>
        </Pressable>
      </ThemedView>
    );
  }
  if (!status?.ready) return null;

  return (
    <ThemedView type="backgroundElement" style={styles.banner}>
      <ThemedText type="smallBold">
        {status.new_since_training} new photos reviewed
      </ThemedText>
      <ThemedText type="small" themeColor="textSecondary">
        Retrain the coach so its tips follow what you kept ({status.kept}) and removed ({status.removed}).
      </ThemedText>
      {error && <Text style={styles.error}>{error}</Text>}
      <View style={styles.row}>
        <Pressable style={styles.button} disabled={training} onPress={retrain}>
          {training ? <ActivityIndicator color="#0B2E19" /> : <Text style={styles.buttonText}>Retrain</Text>}
        </Pressable>
      </View>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  banner: {
    marginHorizontal: Spacing.three,
    marginBottom: Spacing.three,
    padding: Spacing.three,
    borderRadius: Spacing.three,
    gap: Spacing.one,
  },
  row: {
    flexDirection: 'row',
    paddingTop: Spacing.two,
  },
  button: {
    paddingHorizontal: Spacing.four,
    paddingVertical: Spacing.two,
    borderRadius: 999,
    backgroundColor: '#3DDC84',
    minWidth: 96,
    alignItems: 'center',
  },
  buttonText: {
    color: '#0B2E19',
    fontWeight: '700',
  },
  error: {
    color: '#F87171',
  },
  dismiss: {
    paddingTop: Spacing.two,
  },
});
