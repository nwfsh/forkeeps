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

/** The server's judgement of a frame as a photo (server/shots.py). */
export type Shot = {
  /** 0–1, higher is better: the taste model's opinion once trained, simple rules before. */
  score: number;
  scored_by: 'model' | 'rules';
  /** Nothing to fix and a good enough score: auto-capture fires on these. */
  perfect: boolean;
  /** What stops it being perfect: warning codes, "eyes_closed", "low_score". */
  blockers: string[];
};

export type Analysis = {
  width: number;
  height: number;
  faces: Face[];
  /** Most important first. */
  warnings: Warning[];
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
 * Whose taste the review swipes train, in the server's database. There are no accounts yet,
 * so each phone is one person; set EXPO_PUBLIC_PERSON to tell phones apart.
 */
export const PERSON = process.env.EXPO_PUBLIC_PERSON ?? 'me';

export type Verdict = 'keep' | 'remove';

/**
 * Records keep or remove for one photo. Only the analysis goes to the server, never the image.
 * `kind: 'angle'` is for angle-finder frames, which only teach the model about head angle.
 */
export async function sendVerdict(
  photoId: string,
  verdict: Verdict,
  analysis: Analysis | null,
  kind: 'photo' | 'angle' = 'photo'
) {
  const res = await fetch(`${SERVER_URL}/verdicts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ person: PERSON, photo: photoId, verdict, analysis: withoutLandmarks(analysis), kind }),
  });
  if (!res.ok) throw new Error(`Server returned ${res.status}`);
}

/** The analysis minus the 478 face points per face, which the server doesn't need back. */
function withoutLandmarks(analysis: Analysis | null) {
  if (!analysis) return null;
  return { ...analysis, faces: analysis.faces.map(({ landmarks: _, ...face }: Face & { landmarks?: unknown }) => face) };
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
  frames: { id: string; analysis: Analysis }[]
): Promise<{ clusters: AngleCluster[]; skipped: number }> {
  return json(
    await fetch(`${SERVER_URL}/angles/cluster`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ frames: frames.map((f) => ({ id: f.id, analysis: withoutLandmarks(f.analysis) })) }),
    })
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
  // With the person, the server scores the frame with their trained taste (Analysis.shot).
  const res = await fetch(`${SERVER_URL}/analyze?person=${encodeURIComponent(PERSON)}`, {
    method: 'POST',
    body,
    signal,
  });
  if (!res.ok) throw new Error(`Server returned ${res.status}`);
  return res.json();
}
