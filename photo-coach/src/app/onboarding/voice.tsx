import { setAudioModeAsync, useAudioPlayer, useAudioPlayerStatus } from 'expo-audio';
import { router } from 'expo-router';
import { SymbolView } from 'expo-symbols';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useOnboarding } from '@/components/onboarding-provider';
import { GradientBackground, INK, MUTED, PillButton } from '@/components/onboarding-style';
import {
  downloadClip,
  fetchPersonas,
  GOOD_CLIP,
  loadVoiceChoice,
  saveVoiceChoice,
  type Persona,
} from '@/lib/voice';

/**
 * Picks the coach's voice (server/personas.py) before the camera, with a sample of each. The
 * choice is saved where the camera's voice coach reads it, and can still be changed there.
 */
export default function VoiceScreen() {
  const { finish } = useOnboarding();
  const insets = useSafeAreaInsets();
  const [personas, setPersonas] = useState<Persona[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [choice, setChoice] = useState<string | null>(loadVoiceChoice);
  // The sample being fetched or played, by voice.
  // `play` bumps each tap, so tapping the same sample again replays it.
  const [sample, setSample] = useState<{
    persona: string;
    uri: string | null;
    play: number;
  } | null>(null);
  const player = useAudioPlayer(sample?.uri ? { uri: sample.uri } : null);
  const status = useAudioPlayerStatus(player);

  useEffect(() => {
    setAudioModeAsync({ playsInSilentMode: true, interruptionMode: 'duckOthers' }).catch(() => {});
    const controller = new AbortController();
    fetchPersonas(controller.signal)
      .then(setPersonas)
      .catch(
        (e) =>
          !controller.signal.aborted &&
          setError(`Couldn't load the voices. ${e instanceof Error ? e.message : String(e)}`),
      );
    return () => controller.abort();
  }, []);

  // A sample starts once it has loaded; asking before then can be ignored.
  const loaded = status.isLoaded;
  const playCount = sample?.uri ? sample.play : 0;
  useEffect(() => {
    if (!loaded || !playCount) return;
    player.seekTo(0);
    player.play();
  }, [loaded, playCount, player]);

  async function play(persona: Persona) {
    const clip = persona.clips.includes(GOOD_CLIP) ? GOOD_CLIP : persona.clips[0];
    if (!clip) return;
    const play = (sample?.play ?? 0) + 1;
    setSample((current) => ({ persona: persona.id, uri: current?.uri ?? null, play: 0 }));
    try {
      const uri = await downloadClip(persona.id, clip);
      setSample({ persona: persona.id, uri, play });
    } catch {
      setSample(null);
    }
  }

  function choose(id: string | null) {
    setChoice(id);
    if (!id) player.pause();
  }

  function done() {
    player.pause();
    saveVoiceChoice(choice);
    finish();
  }

  const options: { id: string | null; name: string; description: string; persona?: Persona }[] = [
    ...(personas ?? []).map((p) => ({
      id: p.id,
      name: p.name,
      description: p.description,
      persona: p,
    })),
    { id: null, name: 'No voice', description: 'Tips on screen only' },
  ];

  return (
    <View style={styles.screen}>
      <GradientBackground />
      <ScrollView
        contentContainerStyle={[
          styles.content,
          { paddingTop: insets.top + 8, paddingBottom: insets.bottom + 120 },
        ]}>
        <View style={styles.topBar}>
          <Pressable accessibilityRole="button" onPress={() => router.back()} hitSlop={12}>
            <Text style={styles.back}>Back</Text>
          </Pressable>
        </View>

        <View style={styles.copy}>
          <Text style={styles.title}>Pick your coach’s voice</Text>
          <Text style={styles.subtitle}>
            Your coach talks you into the shot while you pose. Tap play to hear each one.
          </Text>
        </View>

        {!personas && !error && <ActivityIndicator color={INK} />}
        {error && <Text style={styles.error}>{error}</Text>}

        <View style={styles.cards}>
          {personas &&
            options.map((option) => {
              const selected = choice === option.id;
              const recorded = !!option.persona?.clips.length;
              const playing =
                sample?.persona === option.id && (sample.uri === null || status.playing);
              return (
                <Pressable
                  key={option.id ?? 'none'}
                  accessibilityRole="radio"
                  accessibilityState={{ selected }}
                  onPress={() => choose(option.id)}
                  style={[styles.card, selected && styles.cardSelected]}>
                  <View style={styles.cardText}>
                    <Text style={styles.name}>{option.name}</Text>
                    <Text style={styles.description}>
                      {option.persona && !recorded ? 'Not recorded yet' : option.description}
                    </Text>
                  </View>
                  {option.persona && recorded && (
                    <Pressable
                      accessibilityRole="button"
                      accessibilityLabel={`Hear ${option.name}`}
                      onPress={() => option.persona && play(option.persona)}
                      hitSlop={8}
                      style={styles.play}>
                      {sample?.persona === option.id && sample.uri === null ? (
                        <ActivityIndicator color={INK} />
                      ) : (
                        <SymbolView
                          name={
                            playing
                              ? {
                                  ios: 'speaker.wave.2.fill',
                                  android: 'volume_up',
                                  web: 'volume_up',
                                }
                              : { ios: 'play.fill', android: 'play_arrow', web: 'play_arrow' }
                          }
                          size={18}
                          tintColor={INK}
                        />
                      )}
                    </Pressable>
                  )}
                  <View style={[styles.radio, selected && styles.radioSelected]}>
                    {selected && <View style={styles.radioDot} />}
                  </View>
                </Pressable>
              );
            })}
        </View>
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: insets.bottom + 16 }]}>
        <PillButton label="Start coaching" onPress={done} />
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
    paddingHorizontal: 24,
    gap: 24,
  },
  topBar: {
    minHeight: 44,
    justifyContent: 'center',
  },
  back: {
    color: INK,
    fontSize: 16,
    fontWeight: '600',
  },
  copy: {
    gap: 10,
  },
  title: {
    color: INK,
    fontSize: 34,
    lineHeight: 40,
    fontWeight: '700',
    letterSpacing: -0.6,
  },
  subtitle: {
    color: MUTED,
    fontSize: 17,
    lineHeight: 24,
  },
  error: {
    color: '#B42318',
    fontSize: 15,
  },
  cards: {
    gap: 12,
  },
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    padding: 18,
    borderRadius: 24,
    backgroundColor: '#FFFFFF',
    borderWidth: 2,
    borderColor: 'transparent',
    shadowColor: '#000000',
    shadowOpacity: 0.06,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 6 },
    elevation: 2,
  },
  cardSelected: {
    borderColor: INK,
  },
  cardText: {
    flex: 1,
    gap: 4,
  },
  name: {
    color: INK,
    fontSize: 18,
    fontWeight: '600',
  },
  description: {
    color: MUTED,
    fontSize: 15,
    lineHeight: 20,
  },
  play: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#F2EEEB',
    alignItems: 'center',
    justifyContent: 'center',
  },
  radio: {
    width: 24,
    height: 24,
    borderRadius: 12,
    borderWidth: 2,
    borderColor: '#C7C2BE',
    alignItems: 'center',
    justifyContent: 'center',
  },
  radioSelected: {
    borderColor: INK,
  },
  radioDot: {
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: INK,
  },
  footer: {
    position: 'absolute',
    left: 20,
    right: 20,
    bottom: 0,
  },
});
