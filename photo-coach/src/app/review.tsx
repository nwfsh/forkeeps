import * as MediaLibrary from 'expo-media-library';
import { router } from 'expo-router';
import { useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { usePhotos } from '@/components/photos-provider';
import { RetrainBanner } from '@/components/retrain-banner';
import { NextCard, RoundButton, SwipeCard, type SwipeCardHandle } from '@/components/swipe-card';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing, FontFamily } from '@/constants/theme';
import { sendVerdict, type Verdict } from '@/lib/server';

/**
 * Hinge-style review of the photos you've taken: swipe right or tap ♥ to keep one, swipe left
 * or tap ✕ to remove it. Each verdict goes to the server's database (the photo's measurements,
 * not the image) so the ranker learns your taste; kept photos are also saved to the phone's
 * Photos library, and removed ones are deleted here.
 */
export default function ReviewScreen() {
  const { photos, keep, remove } = usePhotos();
  // Oldest first, like working through a camera roll.
  const queue = photos.filter((p) => !p.kept).reverse();
  const [reviewed, setReviewed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  // Bumped to put a card back after a failed save, so it remounts in the middle.
  const [attempt, setAttempt] = useState(0);
  const [saving, setSaving] = useState(false);
  const [permission, requestPermission] = MediaLibrary.usePermissions({ writeOnly: true });
  // Why the last kept photo didn't reach the Photos library, if it didn't.
  const [libraryNote, setLibraryNote] = useState<string | null>(null);
  const card = useRef<SwipeCardHandle>(null);
  const [current, next] = queue;

  async function decide(verdict: Verdict) {
    if (!current) return;
    setSaving(true);
    try {
      // Saved before anything changes here: a removed photo is gone for good, so its vote
      // mustn't be lost to a dropped connection.
      await sendVerdict(current.id, verdict, current.analysis);
      setError(null);
      setReviewed((n) => n + 1);
      if (verdict === 'keep') {
        keep(current.id);
        saveToLibrary(current.uri);
      } else remove(current.id);
    } catch (e) {
      setError(
        `Couldn't save that, so nothing changed. ${e instanceof Error ? e.message : String(e)}`,
      );
      setAttempt((n) => n + 1);
    } finally {
      setSaving(false);
    }
  }

  /** Saves a kept photo to Photos. Without access it stays kept here and still taught the coach. */
  async function saveToLibrary(uri: string) {
    try {
      const granted = permission?.granted || (await requestPermission()).granted;
      if (!granted) {
        setLibraryNote('Kept here, but not saved to Photos: allow Photos access in Settings.');
        return;
      }
      await MediaLibrary.Asset.create(uri);
      setLibraryNote(null);
    } catch (e) {
      setLibraryNote(
        `Kept here, but saving to Photos failed: ${e instanceof Error ? e.message : String(e)}`,
      );
    }
  }

  return (
    <ThemedView style={styles.fill}>
      <SafeAreaView style={styles.fill}>
        <View style={styles.header}>
          <ThemedText type="subtitle">Review</ThemedText>
          <Pressable onPress={() => router.back()} style={styles.done} hitSlop={12}>
            <ThemedText type="smallBold">Done</ThemedText>
          </Pressable>
        </View>
        <ThemedText type="small" themeColor="textSecondary" style={styles.hint}>
          {current
            ? `Swipe right to keep (saves to Photos), left to remove · ${queue.length} left`
            : reviewed
              ? `All done: you reviewed ${reviewed} photo${reviewed === 1 ? '' : 's'}.`
              : 'Nothing to review. New photos you take show up here.'}
        </ThemedText>

        {!current && <RetrainBanner />}
        <View style={styles.deck}>
          {next && <NextCard key={next.id} uri={next.uri} />}
          {current && (
            <SwipeCard
              key={`${current.id}/${attempt}`}
              ref={card}
              uri={current.uri}
              onDecide={decide}
            />
          )}
        </View>

        {error && <Text style={styles.error}>{error}</Text>}
        {libraryNote && (
          <ThemedText type="small" themeColor="textSecondary" style={styles.note}>
            {libraryNote}
          </ThemedText>
        )}
        {current && (
          <View style={styles.buttons}>
            <RoundButton
              label="✕"
              color="#F87171"
              disabled={saving}
              onPress={() => card.current?.swipe('remove')}
              accessibilityLabel="Remove photo"
            />
            <RoundButton
              label="♥"
              color="#3DDC84"
              disabled={saving}
              onPress={() => card.current?.swipe('keep')}
              accessibilityLabel="Keep photo"
            />
          </View>
        )}
      </SafeAreaView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  fill: {
    flex: 1,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: Spacing.three,
    paddingTop: Spacing.two,
  },
  done: {
    padding: Spacing.one,
  },
  hint: {
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two,
  },
  deck: {
    flex: 1,
    marginHorizontal: Spacing.three,
    marginBottom: Spacing.three,
  },
  error: {
    fontFamily: FontFamily.body,
    color: '#F87171',
    textAlign: 'center',
    paddingHorizontal: Spacing.three,
    paddingBottom: Spacing.two,
  },
  note: {
    fontFamily: FontFamily.body,
    textAlign: 'center',
    paddingHorizontal: Spacing.three,
    paddingBottom: Spacing.two,
  },
  buttons: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: Spacing.six,
    paddingBottom: Spacing.four,
  },
});
