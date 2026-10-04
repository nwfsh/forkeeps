import Constants from 'expo-constants';
import { File } from 'expo-file-system';

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

export type Analysis = {
  width: number;
  height: number;
  faces: Face[];
  /** Most important first. */
  warnings: Warning[];
  ms: number;
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
 * Whose taste the review swipes train, in the server's database. There are no accounts yet,
 * so each phone is one person; set EXPO_PUBLIC_PERSON to tell phones apart.
 */
export const PERSON = process.env.EXPO_PUBLIC_PERSON ?? 'me';

export type Verdict = 'keep' | 'remove';

/** Records keep or remove for one photo. Only the analysis goes to the server, never the image. */
export async function sendVerdict(photoId: string, verdict: Verdict, analysis: Analysis | null) {
  const res = await fetch(`${SERVER_URL}/verdicts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ person: PERSON, photo: photoId, verdict, analysis }),
  });
  if (!res.ok) throw new Error(`Server returned ${res.status}`);
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
  priorities: { feature: string; prefers: string; share: number }[];
};

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `Server returned ${res.status}`);
  }
  return res.json();
}

export async function fetchModelStatus(): Promise<ModelStatus> {
  return json(await fetch(`${SERVER_URL}/model/${encodeURIComponent(PERSON)}`));
}

export async function retrainModel(): Promise<RetrainResult> {
  return json(await fetch(`${SERVER_URL}/model/${encodeURIComponent(PERSON)}/retrain`, { method: 'POST' }));
}

export async function analyzeFrame(uri: string, signal?: AbortSignal): Promise<Analysis> {
  const body = new FormData();
  // The global fetch is expo/fetch, which can't upload React Native's { uri, name, type }
  // descriptors; it needs a Blob, which expo-file-system's File is.
  body.append('image', new File(uri));
  const res = await fetch(`${SERVER_URL}/analyze`, { method: 'POST', body, signal });
  if (!res.ok) throw new Error(`Server returned ${res.status}`);
  return res.json();
}
