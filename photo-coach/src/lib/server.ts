import Constants from 'expo-constants';
import { File } from 'expo-file-system';

import { loadProfileName, saveProfileName } from '@/lib/profile';

export type FaceBox = { x: number; y: number; w: number; h: number };

export type Face = {
  /** Normalised 0–1 coordinates in the uploaded photo. */
  bbox: FaceBox;
  cut_off: boolean;
  pose?: { yaw: number; pitch: number; roll: number };
  /** Who this is, if they've been enrolled on the server (server/recognize.py). */
  name?: string | null;
};

export type Warning = {
  code: string;
  message: string;
  /** The line the coach's voice says for this warning. */
  clip?: string;
};

/** The server's judgement of a frame as a photo (server/shots.py). */
export type Shot = {
  /** 0–1, higher is better: the taste model's opinion once trained, simple rules before. */
  score: number;
  scored_by: 'model' | 'rules';
  /** Nothing to fix and a good enough score: auto-capture fires on these. */
  perfect: boolean;
  /** What stops it being perfect: warning codes, "eyes_closed", "low_score". */
  blockers: string[];
  /** The change the person's taste model thinks would help most; null without a model. */
  instruction?: { code: string; clip: string; message: string; gain: number } | null;
};

export type Analysis = {
  width: number;
  height: number;
  faces: Face[];
  /** Most important first. */
  warnings: Warning[];
  /** Why the photo can't be judged at all (server/vision.py RED_FLAGS), e.g. "no_person". */
  red_flags: string[];
  ms: number;
  shot?: Shot;
};

const SERVER_PORT = 8000;

/**
 * The analysis server runs on the same PC as the Expo dev server, so reuse its
 * LAN address (e.g. "172.16.136.144:8081"). Set EXPO_PUBLIC_SERVER_URL to override.
 */
function resolveServerUrl() {
  if (process.env.EXPO_PUBLIC_SERVER_URL) return process.env.EXPO_PUBLIC_SERVER_URL;
  const host = Constants.expoConfig?.hostUri?.split(':')[0] ?? 'localhost';
  return `http://${host}:${SERVER_PORT}`;
}

export const SERVER_URL = resolveServerUrl();

/**
 * Whose taste the swipes train and the camera scores with, in the server's database. There are
 * no accounts: each phone is the profile named in onboarding, else EXPO_PUBLIC_PERSON, else "me".
 */
let person = loadProfileName() ?? process.env.EXPO_PUBLIC_PERSON ?? 'me';

export function currentPerson() {
  return person;
}

/** What to tell the person about a red flag, by name, e.g. "Avery isn't in the frame". */
export function redFlagMessage(flag: string): string {
  const name = person ? person.charAt(0).toUpperCase() + person.slice(1) : 'You';
  const messages: Record<string, string> = {
    no_person: `${name} isn't in the frame`,
    no_face: `${name}'s face isn't in view`,
    face_cut_off: `${name} isn't fully in the frame`,
    face_too_small: `Get closer: ${name}'s face is too small to read`,
    several_people: `Someone else is in the frame`,
    face_covered: `Something is covering ${name}'s face`,
  };
  return messages[flag] ?? `Can't see ${name} clearly`;
}

/** Makes `name` this phone's profile from now on. */
export function setPerson(name: string) {
  person = name;
  saveProfileName(name);
}

export type Verdict = 'keep' | 'remove';

/**
 * Records keep or remove for one photo. Only the analysis goes to the server, never the image.
 * `kind: 'angle'` is for angle-finder frames, which only teach the model about head angle.
 */
export async function sendVerdict(
  photoId: string,
  verdict: Verdict,
  analysis: Analysis | null,
  kind: 'photo' | 'angle' = 'photo',
) {
  const res = await fetch(`${SERVER_URL}/verdicts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      person,
      photo: photoId,
      verdict,
      analysis: withoutLandmarks(analysis),
      kind,
    }),
  });
  if (!res.ok) throw new Error(`Server returned ${res.status}`);
}

/**
 * Records that `winner` was picked over `loser`, or with `tie` that the two are equally good.
 * Only their analyses go, never the images.
 */
export async function sendPick(
  winner: { id: string; analysis: Analysis },
  loser: { id: string; analysis: Analysis },
  tie = false,
) {
  const res = await fetch(`${SERVER_URL}/picks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      person,
      winner: { id: winner.id, analysis: withoutLandmarks(winner.analysis) },
      loser: { id: loser.id, analysis: withoutLandmarks(loser.analysis) },
      tie,
    }),
  });
  if (!res.ok) throw new Error(`Server returned ${res.status}`);
}

/** A pick in a comparing session, as /pairs/next takes it. */
export type SessionPick = { winner: string; loser: string } | { a: string; b: string; tie: true };

export type NextPair = {
  pair: [string, string] | null;
  /** Why to stop asking ("clear", "predictable", "limit"), or null to keep going. */
  stop: string | null;
  picks: number;
  min: number;
  max: number;
};

/** The next pair to compare and whether to stop, decided like the Streamlit compare tool. */
export async function nextPair(
  candidates: { id: string; analysis: Analysis }[],
  picks: SessionPick[],
  skipped: [string, string][],
): Promise<NextPair> {
  return json(
    await fetch(`${SERVER_URL}/pairs/next`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        candidates: candidates.map((c) => ({ id: c.id, analysis: withoutLandmarks(c.analysis) })),
        picks,
        skipped,
      }),
    }),
  );
}

/** The analysis minus the 478 face points per face, which the server doesn't need back. */
function withoutLandmarks(analysis: Analysis | null) {
  if (!analysis) return null;
  return {
    ...analysis,
    faces: analysis.faces.map(({ landmarks: _, ...face }: Face & { landmarks?: unknown }) => face),
  };
}

export type AngleCluster = {
  /** Id of the frame chosen to show this angle. */
  frame: string;
  /** How many frames were at this angle. */
  size: number;
  pose: { yaw: number; pitch: number; roll: number };
  /** e.g. "Left side, chin up". */
  label: string;
};

/** Groups angle-finder frames by head angle; one typical frame per group, biggest first. */
export async function clusterAngles(
  frames: { id: string; analysis: Analysis }[],
): Promise<{ clusters: AngleCluster[]; skipped: number }> {
  return json(
    await fetch(`${SERVER_URL}/angles/cluster`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        frames: frames.map((f) => ({ id: f.id, analysis: withoutLandmarks(f.analysis) })),
      }),
    }),
  );
}

/**
 * Picks about twenty varied frames from a recording for onboarding's swipes; their ids, most
 * typical first. `usable` is how many frames could be measured at all.
 */
export async function pickSnapshots(
  frames: { id: string; analysis: Analysis }[],
  count = 20,
): Promise<{ snapshots: string[]; usable: number }> {
  return json(
    await fetch(`${SERVER_URL}/snapshots`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        frames: frames.map((f) => ({ id: f.id, analysis: withoutLandmarks(f.analysis) })),
        count,
      }),
    }),
  );
}

/** Review counts from GET /model/{person}; `ready` once enough photos are new since training. */
export type ModelStatus = {
  reviewed: number;
  kept: number;
  removed: number;
  new_since_training: number;
  retrain_after: number;
  ready: boolean;
  last_trained: string | null;
};

export type RetrainResult = {
  reviewed: number;
  confidence: number;
  /** Most influential first, worded like "Smiling, more of it". */
  priorities: { feature: string; prefers: string; share: number; weight: number }[];
};

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `Server returned ${res.status}`);
  }
  return res.json();
}

export async function fetchModelStatus(): Promise<ModelStatus> {
  return json(await fetch(`${SERVER_URL}/model/${encodeURIComponent(person)}`));
}

export async function retrainModel(): Promise<RetrainResult> {
  return json(
    await fetch(`${SERVER_URL}/model/${encodeURIComponent(person)}/retrain`, { method: 'POST' }),
  );
}

export async function analyzeFrame(uri: string, signal?: AbortSignal): Promise<Analysis> {
  const body = new FormData();
  // The global fetch is expo/fetch, which can't upload React Native's { uri, name, type }
  // descriptors; it needs a Blob, which expo-file-system's File is.
  body.append('image', new File(uri));
  // With the person, the server scores the frame with their trained taste (Analysis.shot).
  const res = await fetch(`${SERVER_URL}/analyze?person=${encodeURIComponent(person)}`, {
    method: 'POST',
    body,
    signal,
  });
  if (!res.ok) throw new Error(`Server returned ${res.status}`);
  return res.json();
}
