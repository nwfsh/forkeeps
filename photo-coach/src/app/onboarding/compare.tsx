import { Image } from 'expo-image';
import { router } from 'expo-router';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { SymbolView } from 'expo-symbols';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useOnboarding, type Snapshot } from '@/components/onboarding-provider';
import {
  GradientBackground,
  INK,
  MUTED,
  PillButton,
  StepDots,
} from '@/components/onboarding-style';
import { nextPair, retrainModel, sendPick, type NextPair, type SessionPick } from '@/lib/server';

// How long the chosen photo shows its check before the next pair.
const CHOSEN_MS = 450;

/**
 * "Which do you prefer?" on the recording's snapshots, run like the Streamlit compare tool
 * (server/compare.py): the server picks each pair, usually the one the model is least sure
 * about, and says when to stop (15 to 40 picks, once the pattern is clear). Tap the one you like
 * more, "It's a tie" when they're equally good (which teaches that what differs doesn't matter),
 * or "Can't decide" to skip. Then the profile is trained from it all (server/retrain.py).
 */
export default function CompareScreen() {
  const { snapshots, setResults } = useOnboarding();
  // Ids from different recordings must not collide on the server.
  const [session] = useState(() => String(Date.now()));
  const byId = useMemo(() => new Map(snapshots.map((s) => [s.id, s])), [snapshots]);
  const [picks, setPicks] = useState<SessionPick[]>([]);
  const [skipped, setSkipped] = useState<[string, string][]>([]);
  const [step, setStep] = useState<NextPair | null>(null);
  // True while a pair is being fetched or a pick saved; the first pair is fetched straight away.
  const [busy, setBusy] = useState(true);
  const [training, setTraining] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The photo just tapped, shown with a check until its pick is sent.
  const [chosen, setChosen] = useState<string | null>(null);
  const insets = useSafeAreaInsets();

  const train = useCallback(async () => {
    setTraining(true);
    setError(null);
    try {
      setResults(await retrainModel());
      router.replace('/onboarding/results');
    } catch (e) {
      setError(`Couldn't build your profile. ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setTraining(false);
    }
  }, [setResults]);

  // Ask the server for the next pair after every pick, tie or skip.
  useEffect(() => {
    let cancelled = false;
    nextPair(snapshots, picks, skipped)
      .then((next) => {
        if (cancelled) return;
        setStep(next);
        setError(null);
        if ((next.stop || !next.pair) && picks.length > 0) train();
      })
      .catch(
        (e) =>
          !cancelled &&
          setError(`Couldn't reach the server. ${e instanceof Error ? e.message : String(e)}`),
      )
      .finally(() => !cancelled && setBusy(false));
    return () => {
      cancelled = true;
    };
  }, [snapshots, picks, skipped, train]);

  const pair = step?.pair && !step.stop ? step.pair.map((id) => byId.get(id)) : null;
  const [a, b] = pair ?? [];

  /** Shows the tapped photo as chosen for a moment, then sends the pick. */
  function tap(winner: Snapshot, loser: Snapshot) {
    setBusy(true);
    setChosen(winner.id);
    setTimeout(() => choose(winner, loser), CHOSEN_MS);
  }

  async function choose(winner: Snapshot, loser: Snapshot, tie = false) {
    setBusy(true);
    try {
      await sendPick(
        { id: `onboarding-${session}-${winner.id}`, analysis: winner.analysis },
        { id: `onboarding-${session}-${loser.id}`, analysis: loser.analysis },
        tie,
      );
      setChosen(null);
      setPicks((list) => [
        ...list,
        tie ? { a: winner.id, b: loser.id, tie: true } : { winner: winner.id, loser: loser.id },
      ]);
    } catch (e) {
      setError(`Couldn't save that. ${e instanceof Error ? e.message : String(e)}`);
      setChosen(null);
      setBusy(false);
    }
  }

  const count = picks.length;
  const min = step?.min ?? 15;
  const max = step?.max ?? 40;
  // Counts toward the minimum first, then toward the most it will ask.
  const goal = count < min ? min : max;

  return (
    <View style={styles.screen}>
      <GradientBackground />
      <View
        style={[
          styles.content,
          { paddingTop: insets.top + 36, paddingBottom: insets.bottom + 16 },
        ]}>
        <StepDots step={3} steps={3} />
        <View style={styles.heading}>
          <Text style={styles.title}>Which do you prefer?</Text>
          <Text style={styles.lead}>
            {training ? 'Building your profile…' : 'Tap the one you like more.'}
          </Text>
        </View>

        {/* The photos and progress in the card, near the top; the other choices at the bottom. */}
        <View style={styles.body}>
          <View style={styles.card}>
            {a && b && !training && (
              <View style={styles.pair}>
                {(
                  [
                    [a, b, 'A'],
                    [b, a, 'B'],
                  ] as const
                ).map(([shown, other, label]) => {
                  const isChosen = shown.id === chosen;
                  const faded = chosen !== null && !isChosen;
                  return (
                    <Pressable
                      key={shown.id}
                      accessibilityRole="button"
                      accessibilityLabel={`Pick frame ${label}`}
                      disabled={busy}
                      onPress={() => tap(shown, other)}
                      style={({ pressed }) => [
                        styles.photoCard,
                        isChosen && styles.photoChosen,
                        faded && styles.photoFaded,
                        pressed && !chosen && styles.pressed,
                      ]}>
                      <Image source={{ uri: shown.uri }} style={styles.photo} contentFit="cover" />
                      {isChosen && (
                        <View style={styles.check}>
                          <SymbolView
                            name={{ ios: 'checkmark', android: 'check', web: 'check' }}
                            size={16}
                            weight="bold"
                            tintColor="#FFFFFF"
                          />
                        </View>
                      )}
                      <View style={[styles.label, isChosen ? styles.labelDark : styles.labelLight]}>
                        <Text style={[styles.labelText, isChosen && styles.labelTextDark]}>
                          Frame {label}
                        </Text>
                      </View>
                    </Pressable>
                  );
                })}
              </View>
            )}

            {(training || (busy && !pair)) && (
              <View style={styles.center}>
                <ActivityIndicator color={INK} />
              </View>
            )}

            {!training && !busy && step && !step.pair && count === 0 && (
              <View style={styles.center}>
                <Text style={styles.lead}>
                  Not enough snapshots to compare. Record again with your face in view.
                </Text>
                <PillButton
                  label="Record again"
                  onPress={() => router.replace('/onboarding/record')}
                />
              </View>
            )}

            {error && (
              <View style={styles.errorBox}>
                <Text style={styles.error}>{error}</Text>
                {count > 0 && !training && (
                  <PillButton label="Try building my profile again" onPress={train} />
                )}
              </View>
            )}

            {a && b && !training && (
              <>
                <View style={styles.progress}>
                  <Text style={styles.count}>
                    {count} of {goal}
                  </Text>
                  <View style={styles.track}>
                    <View style={[styles.bar, { width: `${Math.min(1, count / goal) * 100}%` }]} />
                  </View>
                </View>
              </>
            )}
          </View>

          {a && b && !training && (
            <View style={styles.actions}>
              <Pressable
                accessibilityRole="button"
                disabled={busy}
                onPress={() => choose(a, b, true)}
                style={({ pressed }) => [styles.tie, pressed && styles.pressed]}>
                <Text style={styles.tieText}>Both the same: it’s a tie</Text>
              </Pressable>
              <Pressable
                accessibilityRole="button"
                disabled={busy}
                onPress={() => {
                  setBusy(true);
                  setSkipped((list) => [...list, [a.id, b.id]]);
                }}
                hitSlop={8}>
                <Text style={styles.skip}>Can’t decide? Skip this pair</Text>
              </Pressable>
              {/* From the minimum on, they can stop whenever they've had enough. */}
              {count >= min && (
                <View style={styles.doneRow}>
                  <Text style={styles.doneQuestion}>Done deciding?</Text>
                  <Pressable
                    accessibilityRole="button"
                    disabled={busy}
                    onPress={train}
                    style={({ pressed }) => [styles.doneButton, pressed && styles.pressed]}>
                    <Text style={styles.doneText}>Show my results</Text>
                    <SymbolView
                      name={{ ios: 'arrow.right', android: 'arrow_forward', web: 'arrow_forward' }}
                      size={16}
                      weight="semibold"
                      tintColor="#FFFFFF"
                    />
                  </Pressable>
                </View>
              )}
            </View>
          )}
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
  content: {
    flex: 1,
    paddingHorizontal: 16,
    gap: 16,
  },
  title: {
    color: INK,
    fontSize: 34,
    lineHeight: 40,
    fontWeight: '700',
    letterSpacing: -0.6,
  },
  heading: {
    gap: 8,
  },
  body: {
    flex: 1,
    justifyContent: 'space-between',
  },
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: 32,
    padding: 12,
    paddingTop: 32,
    paddingBottom: 16,
    gap: 16,
    shadowColor: '#000000',
    shadowOpacity: 0.06,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: 8 },
    elevation: 3,
  },
  lead: {
    paddingHorizontal: 4,
    color: MUTED,
    fontSize: 17,
    lineHeight: 23,
  },
  // The two photos side by side, each half the card's width.
  pair: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
  },
  photoCard: {
    flex: 1,
    // Tall, like a phone photo, but not quite twice as high as wide.
    aspectRatio: 0.58,
    borderRadius: 20,
    overflow: 'hidden',
    backgroundColor: '#EEE9E6',
    borderWidth: 3,
    borderColor: 'transparent',
  },
  photoChosen: {
    borderColor: INK,
  },
  photoFaded: {
    opacity: 0.4,
  },
  photo: {
    flex: 1,
  },
  check: {
    position: 'absolute',
    top: 12,
    right: 12,
    width: 30,
    height: 30,
    borderRadius: 15,
    backgroundColor: INK,
    alignItems: 'center',
    justifyContent: 'center',
  },
  label: {
    position: 'absolute',
    bottom: 10,
    alignSelf: 'center',
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 999,
  },
  labelDark: {
    backgroundColor: INK,
  },
  labelLight: {
    backgroundColor: 'rgba(255,255,255,0.85)',
  },
  labelText: {
    color: INK,
    fontSize: 15,
    fontWeight: '600',
  },
  labelTextDark: {
    color: '#FFFFFF',
  },
  center: {
    alignItems: 'center',
    gap: 16,
    paddingVertical: 24,
  },
  errorBox: {
    gap: 12,
  },
  error: {
    color: '#B42318',
    fontSize: 15,
    textAlign: 'center',
  },
  progress: {
    gap: 8,
    paddingHorizontal: 4,
  },
  count: {
    color: INK,
    fontSize: 16,
  },
  track: {
    height: 10,
    borderRadius: 5,
    backgroundColor: '#EEE9E6',
    overflow: 'hidden',
  },
  bar: {
    height: 10,
    borderRadius: 5,
    backgroundColor: INK,
  },
  actions: {
    alignItems: 'center',
    gap: 12,
  },
  tie: {
    alignSelf: 'stretch',
    height: 48,
    borderRadius: 999,
    borderWidth: 1.5,
    borderColor: INK,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pressed: {
    opacity: 0.6,
  },
  tieText: {
    color: INK,
    fontSize: 16,
    fontWeight: '600',
  },
  skip: {
    color: MUTED,
    fontSize: 16,
  },
  doneRow: {
    alignSelf: 'stretch',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    paddingTop: 4,
  },
  doneQuestion: {
    flexShrink: 1,
    color: INK,
    fontSize: 16,
    fontWeight: '600',
  },
  doneButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    height: 46,
    paddingHorizontal: 20,
    borderRadius: 999,
    backgroundColor: INK,
  },
  doneText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600',
  },
});
