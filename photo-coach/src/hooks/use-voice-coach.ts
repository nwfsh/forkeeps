import { setAudioModeAsync, useAudioPlayer } from 'expo-audio';
import { useEffect, useRef, useState } from 'react';

import { downloadClip, fetchPersonas, GOOD_CLIP, loadVoiceChoice, saveVoiceChoice, type Persona } from '@/lib/voice';

/** A tip has to hold this long before it's spoken, so a flickering result doesn't chatter. */
const HOLD_MS = 1000;
/** Shortest gap between the starts of two lines. */
const MIN_GAP_MS = 2500;
/** An unfixed tip is said again after this long. */
const REPEAT_MS = 12000;
const CHECK_MS = 250;
/** A line that hasn't loaded after this long is dropped. */
const LOAD_MS = 3000;
const RETRY_MS = 5000;

/**
 * Speaks the current tip in the chosen persona's voice. `clip` is the line to say
 * (see CLIPS in server/personas.py), or null to stay quiet.
 * Lines never cut each other off, and praise is said once rather than repeated.
 */
export function useVoiceCoach(clip: string | null) {
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [choice, setChoice] = useState<string | null>(loadVoiceChoice);
  const player = useAudioPlayer(null);
  const spoken = useRef({ key: '', at: 0 });
  /** Where each line downloaded this session is on the phone. */
  const local = useRef(new Map<string, string>());
  /** When a line was handed to the player and is still loading, else 0. */
  const loading = useRef(0);

  // Only voices with something recorded can be picked.
  const available = personas.filter((p) => p.clips.length > 0);
  const persona = available.find((p) => p.id === choice) ?? null;

  useEffect(() => {
    // The coach should be heard with the ringer off, and over music rather than stopping it.
    setAudioModeAsync({ playsInSilentMode: true, interruptionMode: 'duckOthers' }).catch(() => {});
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();

    async function load() {
      try {
        const list = await fetchPersonas(controller.signal);
        if (!cancelled) setPersonas(list);
      } catch {
        // The server may not be up yet; keep trying quietly, the camera screen shows the error.
        if (!cancelled) timer = setTimeout(load, RETRY_MS);
      }
    }

    load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
      controller.abort();
    };
  }, []);

  useEffect(() => {
    if (!persona) return;
    // Fetched again each launch, so lines re-recorded on the server replace the old ones.
    for (const name of persona.clips) {
      const key = `${persona.id}/${name}`;
      if (local.current.has(key)) continue;
      downloadClip(persona.id, name)
        .then((uri) => local.current.set(key, uri))
        .catch((e) => console.warn(`Couldn't download voice line ${key}:`, e));
    }
  }, [persona]);

  useEffect(() => {
    if (!persona || !clip || !persona.clips.includes(clip)) return;
    const key = `${persona.id}/${clip}`;
    const since = Date.now();

    const timer = setInterval(() => {
      const now = Date.now();
      if (loading.current) {
        // Asking a line to play before it has loaded can be ignored, so wait for it.
        if (player.isLoaded) player.play();
        else if (now - loading.current < LOAD_MS) return;
        loading.current = 0;
        return;
      }
      const last = spoken.current;
      if (now - since < HOLD_MS || now - last.at < MIN_GAP_MS || player.playing) return;
      if (last.key === key && (clip === GOOD_CLIP || now - last.at < REPEAT_MS)) return;
      const uri = local.current.get(key);
      if (!uri) return;
      spoken.current = { key, at: now };
      player.replace({ uri });
      loading.current = now;
    }, CHECK_MS);
    return () => clearInterval(timer);
  }, [clip, persona, player]);

  /** Steps through off, then each voice in turn. */
  function next() {
    const ids = [null, ...available.map((p) => p.id)];
    const id = ids[(ids.indexOf(persona?.id ?? null) + 1) % ids.length];
    if (!id) player.pause();
    setChoice(id);
    saveVoiceChoice(id);
  }

  return { persona, canSpeak: available.length > 0, next };
}
