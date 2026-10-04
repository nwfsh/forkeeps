import Constants from 'expo-constants';
import { File } from 'expo-file-system';

export type FaceBox = { x: number; y: number; w: number; h: number };

export type Face = {
  /** Normalised 0–1 coordinates in the uploaded photo. */
  bbox: FaceBox;
  cut_off: boolean;
  pose?: { yaw: number; pitch: number; roll: number };
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

export async function analyzeFrame(uri: string, signal?: AbortSignal): Promise<Analysis> {
  const body = new FormData();
  // Expo's fetch only uploads real files; it rejects React Native's { uri, name, type } descriptor.
  body.append('image', new File(uri) as unknown as Blob);
  const res = await fetch(`${SERVER_URL}/analyze`, { method: 'POST', body, signal });
  if (!res.ok) throw new Error(`Server returned ${res.status}`);
  return res.json();
}
