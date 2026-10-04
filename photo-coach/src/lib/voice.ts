import { Directory, File, Paths } from 'expo-file-system';

import { SERVER_URL } from '@/lib/server';

export type Persona = {
  id: string;
  name: string;
  description: string;
  /** The lines that have been recorded for this voice on the server. */
  clips: string[];
};

/** What the coach says when there's nothing to fix. */
export const GOOD_CLIP = 'looks_good';

const choiceFile = new File(Paths.document, 'voice.json');
const clipsDir = new Directory(Paths.cache, 'voices');

export async function fetchPersonas(signal?: AbortSignal): Promise<Persona[]> {
  const res = await fetch(`${SERVER_URL}/personas`, { signal });
  if (!res.ok) throw new Error(`Server returned ${res.status}`);
  return res.json();
}

function clipUrl(persona: string, clip: string) {
  return `${SERVER_URL}/voice/${persona}/${clip}`;
}

/**
 * Copies one line onto the phone and returns where it is. Playing from a local .mp3 starts
 * straight away and doesn't depend on the player streaming from the server.
 */
export async function downloadClip(persona: string, clip: string): Promise<string> {
  const dir = new Directory(clipsDir, persona);
  dir.create({ idempotent: true, intermediates: true });
  const file = await File.downloadFileAsync(clipUrl(persona, clip), new File(dir, `${clip}.mp3`), {
    idempotent: true,
  });
  return file.uri;
}

/** The persona picked last time, or null for no voice. */
export function loadVoiceChoice(): string | null {
  try {
    return choiceFile.exists ? (JSON.parse(choiceFile.textSync()).persona ?? null) : null;
  } catch {
    // A broken or unreadable settings file just means starting with the voice off.
    return null;
  }
}

export function saveVoiceChoice(persona: string | null) {
  try {
    choiceFile.write(JSON.stringify({ persona }));
  } catch {
    // Losing the choice only costs a tap next launch.
  }
}
