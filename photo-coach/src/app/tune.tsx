import { router } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { usePhotos } from '@/components/photos-provider';
import { NextCard, RoundButton, SwipeCard, type SwipeCardHandle } from '@/components/swipe-card';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing, FontFamily } from '@/constants/theme';
import type { Photo } from '@/lib/photos';
import {
  fetchUncertain,
  retrainModel,
  sendVerdict,
  type RetrainResult,
  type Verdict,
} from '@/lib/server';

const GREEN = '#3DDC84';
const RED = '#F87171';

type Card = { photo: Photo; score: number };
type Phase = 'loading' | 'swiping' | 'training' | 'results' | 'unavailable';

/**
 * Tune the taste model you already have: the server picks the photos it's least sure about,
 * you swipe them Hinge-style (right likes it, left doesn't; nothing is deleted), and it retrains
 * on everything it knows plus these swipes, then shows what changed.
 */
export default function TuneScreen() {
  const { photos, keep } = usePhotos();
  const [phase, setPhase] = useState<Phase>('loading');
  const [cards, setCards] = useState<Card[]>([]);
  const [index, setIndex] = useState(0);
  const [swiped, setSwiped] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Bumped to put a card back after a failed save, so it remounts in the middle.
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<RetrainResult | null>(null);
  const card = useRef<SwipeCardHandle>(null);
  // The photos as they were when the screen opened; keeping one mustn't reshuffle the deck.
  const [measured] = useState(() => photos.filter((p) => p.analysis));
  const tooFew = measured.length < 2;

  useEffect(() => {
    if (tooFew) return;
    let cancelled = false;
    fetchUncertain(measured.map((p) => ({ id: p.id, analysis: p.analysis })))
      .then((chosen) => {
        if (cancelled) return;
        const byId = new Map(measured.map((p) => [p.id, p]));
        const deck = chosen.flatMap(({ id, score }) =>
          byId.has(id) ? [{ photo: byId.get(id)!, score }] : [],
        );
        setCards(deck);
        setPhase(deck.length ? 'swiping' : 'unavailable');
        if (!deck.length)
          setError('None of your photos could be measured well enough to tune with.');
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
        setPhase('unavailable');
      });
    return () => {
      cancelled = true;
    };
  }, [measured, tooFew]);

  async function decide(verdict: Verdict) {
    const current = cards[index];
    if (!current) return;
    setSaving(true);
    try {
      // The same verdict Review saves: swiping a photo again replaces its old one.
      await sendVerdict(current.photo.id, verdict, current.photo.analysis);
      if (verdict === 'keep') keep(current.photo.id);
      setError(null);
      setSwiped((n) => n + 1);
      setIndex((i) => i + 1);
      if (index + 1 >= cards.length) train();
    } catch (e) {
      setError(
        `Couldn't save that, so nothing changed. ${e instanceof Error ? e.message : String(e)}`,
      );
      setAttempt((n) => n + 1);
    } finally {
      setSaving(false);
    }
  }

  async function train() {
    setPhase('training');
    setError(null);
    try {
      setResult(await retrainModel());
      setPhase('results');
    } catch (e) {
      setError(`Couldn't retrain. ${e instanceof Error ? e.message : String(e)}`);
      setPhase('swiping');
    }
  }

  const current = cards[index];
  const next = cards[index + 1];

  return (
    <ThemedView style={styles.fill}>
      <SafeAreaView style={styles.fill}>
        <View style={styles.header}>
          <ThemedText type="subtitle">Tune your taste</ThemedText>
          <Pressable onPress={() => router.back()} style={styles.done} hitSlop={12}>
            <ThemedText type="smallBold">Done</ThemedText>
          </Pressable>
        </View>

        {tooFew && (
          <View style={styles.center}>
            <ThemedText style={styles.centerText}>
              Take a few more photos first: there need to be at least two the coach has measured.
            </ThemedText>
          </View>
        )}

        {phase === 'loading' && !tooFew && (
          <View style={styles.center}>
            <ActivityIndicator />
            <ThemedText themeColor="textSecondary">
              Finding the photos your coach is least sure about…
            </ThemedText>
          </View>
        )}

        {phase === 'unavailable' && (
          <View style={styles.center}>
            <ThemedText style={styles.centerText}>{error}</ThemedText>
          </View>
        )}

        {phase === 'swiping' && (
          <>
            <ThemedText type="small" themeColor="textSecondary" style={styles.hint}>
              {current
                ? `Right if you like it, left if you don't. Nothing gets deleted. ${index + 1} of ${cards.length}`
                : 'Retraining…'}
            </ThemedText>
            {current && (
              <ThemedText type="small" themeColor="textSecondary" style={styles.hint}>
                Your coach gives this one {Math.round(current.score * 100)}%: it can&apos;t tell
                yet.
              </ThemedText>
            )}
            <View style={styles.deck}>
              {next && <NextCard key={next.photo.id} uri={next.photo.uri} />}
              {current && (
                <SwipeCard
                  key={`${current.photo.id}/${attempt}`}
                  ref={card}
                  uri={current.photo.uri}
                  onDecide={decide}
                />
              )}
            </View>
            {error && <Text style={styles.error}>{error}</Text>}
            {current && (
              <View style={styles.buttons}>
                <RoundButton
                  label="✕"
                  color={RED}
                  disabled={saving}
                  onPress={() => card.current?.swipe('remove')}
                  accessibilityLabel="Not my style"
                />
                <RoundButton
                  label="♥"
                  color={GREEN}
                  disabled={saving}
                  onPress={() => card.current?.swipe('keep')}
                  accessibilityLabel="I like this one"
                />
              </View>
            )}
            {swiped > 0 && current && (
              <Pressable style={styles.now} disabled={saving} onPress={train} hitSlop={8}>
                <ThemedText type="smallBold">
                  Retrain now with {swiped} swipe{swiped === 1 ? '' : 's'}
                </ThemedText>
              </Pressable>
            )}
          </>
        )}

        {phase === 'training' && (
          <View style={styles.center}>
            <ActivityIndicator />
            <ThemedText themeColor="textSecondary">
              Retraining on everything you&apos;ve taught it…
            </ThemedText>
          </View>
        )}

        {phase === 'results' && result && <Results result={result} swiped={swiped} />}
      </SafeAreaView>
    </ThemedView>
  );
}

/** What the coach cares about now, next to what it cared about before this tune. */
function Results({ result, swiped }: { result: RetrainResult; swiped: number }) {
  const before = result.before;
  const shown = result.priorities.slice(0, 3);
  const wasTop = new Set(before?.priorities.map((p) => p.feature));
  const percent = (value: number | null | undefined) =>
    value == null ? '–' : `${Math.round(value * 100)}%`;

  return (
    <View style={styles.results}>
      <ThemedText>
        Retrained with your {swiped} new swipe{swiped === 1 ? '' : 's'} and everything from before.
      </ThemedText>
      <ThemedView type="backgroundElement" style={styles.panel}>
        <ThemedText type="smallBold">How sure it is</ThemedText>
        <ThemedText>
          {before ? `${percent(before.confidence)} → ` : ''}
          {percent(result.confidence)}
        </ThemedText>
      </ThemedView>
      <ThemedView type="backgroundElement" style={styles.panel}>
        <ThemedText type="smallBold">What it looks for now</ThemedText>
        {shown.map((p) => (
          <ThemedText key={p.feature}>
            • {p.prefers} ({Math.round(p.share * 100)}%)
            {before && !wasTop.has(p.feature) ? '  new' : ''}
          </ThemedText>
        ))}
      </ThemedView>
      {before && (
        <ThemedView type="backgroundElement" style={styles.panel}>
          <ThemedText type="smallBold">Before</ThemedText>
          {before.priorities.map((p) => (
            <ThemedText key={p.feature} themeColor="textSecondary">
              • {p.prefers} ({Math.round(p.share * 100)}%)
            </ThemedText>
          ))}
        </ThemedView>
      )}
      <Pressable style={styles.finish} onPress={() => router.back()}>
        <Text style={styles.finishText}>Done</Text>
      </Pressable>
    </View>
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
  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.three,
    padding: Spacing.four,
  },
  centerText: {
    fontFamily: FontFamily.body,
    textAlign: 'center',
  },
  hint: {
    paddingHorizontal: Spacing.three,
    paddingTop: Spacing.two,
  },
  deck: {
    flex: 1,
    margin: Spacing.three,
  },
  error: {
    fontFamily: FontFamily.body,
    color: RED,
    textAlign: 'center',
    paddingHorizontal: Spacing.three,
    paddingBottom: Spacing.two,
  },
  buttons: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: Spacing.six,
    paddingBottom: Spacing.two,
  },
  now: {
    alignSelf: 'center',
    padding: Spacing.two,
    marginBottom: Spacing.two,
  },
  results: {
    flex: 1,
    padding: Spacing.three,
    gap: Spacing.three,
  },
  panel: {
    padding: Spacing.three,
    borderRadius: Spacing.three,
    gap: Spacing.one,
  },
  finish: {
    alignSelf: 'center',
    marginTop: 'auto',
    minWidth: 200,
    alignItems: 'center',
    paddingVertical: Spacing.three,
    borderRadius: 999,
    backgroundColor: GREEN,
  },
  finishText: {
    fontFamily: FontFamily.bodyBold,
    color: '#0B2E19',
    fontSize: 16,
  },
});
