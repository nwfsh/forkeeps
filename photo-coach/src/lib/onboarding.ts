import { File, Paths } from 'expo-file-system';

/**
 * Onboarding data. Everything here is mock data shaped like the server's ranker
 * (server/ranker.py), so swapping in real photos and results only changes where the
 * data comes from, not the screens.
 */

export type PhotoOption = {
  id: string;
  /** Real photo, once the server supplies pairs. Without it the card shows a placeholder. */
  uri?: string;
  placeholderLabel: string;
  placeholderColor: string;
};

export type Pick = { winner: string; loser: string };

/** One row of Ranker.priorities(). */
export type Priority = {
  feature: string;
  label: string;
  /** Positive: they pick more of it. Negative: less. */
  weight: number;
  /** Share of total influence, 0–1. */
  share: number;
};

/** Matches the results page in server/compare.py: clear ≥ 0.9, likely ≥ 0.7. */
export type Confidence = 'clear' | 'likely' | 'unclear';

export type StyleResults = { priorities: Priority[]; confidence: Confidence };

// TODO: replace with pairs from the server (Ranker.next_pair) of the user's own photos.
export const MOCK_PAIRS: [PhotoOption, PhotoOption][] = [
  [
    { id: 'a1', placeholderLabel: 'Big smile', placeholderColor: '#F4C7A1' },
    { id: 'b1', placeholderLabel: 'Soft smile', placeholderColor: '#A8C5E6' },
  ],
  [
    { id: 'a2', placeholderLabel: 'Head tilted', placeholderColor: '#B9DDB5' },
    { id: 'b2', placeholderLabel: 'Head straight', placeholderColor: '#E6B8D2' },
  ],
  [
    { id: 'a3', placeholderLabel: 'Close up', placeholderColor: '#C9C1EE' },
    { id: 'b3', placeholderLabel: 'Further away', placeholderColor: '#F1DE9E' },
  ],
  [
    { id: 'a4', placeholderLabel: 'Looking at lens', placeholderColor: '#A6DCD6' },
    { id: 'b4', placeholderLabel: 'Looking away', placeholderColor: '#F2B8B0' },
  ],
  [
    { id: 'a5', placeholderLabel: 'Sharp', placeholderColor: '#D3D7A6' },
    { id: 'b5', placeholderLabel: 'Slightly soft', placeholderColor: '#B7CBE0' },
  ],
  [
    { id: 'a6', placeholderLabel: 'Chin down', placeholderColor: '#E9C4A6' },
    { id: 'b6', placeholderLabel: 'Chin level', placeholderColor: '#BFD8C0' },
  ],
];

// TODO: replace with the server's results once the user has made their picks.
export const MOCK_RESULTS: StyleResults = {
  confidence: 'likely',
  priorities: [
    { feature: 'smile', label: 'Smiling', weight: 1.4, share: 0.34 },
    { feature: 'eye_contact', label: 'Looking at the camera', weight: 0.9, share: 0.22 },
    { feature: 'head_straight', label: 'Head held straight', weight: -0.6, share: 0.15 },
    { feature: 'sharpness', label: 'Sharp focus', weight: 0.5, share: 0.12 },
    { feature: 'face_size', label: 'Face fills the frame', weight: 0.4, share: 0.1 },
  ],
};

const stateFile = new File(Paths.document, 'onboarding.json');

/** Set EXPO_PUBLIC_SHOW_ONBOARDING=1 to see onboarding on every launch while designing it. */
const ALWAYS_SHOW = process.env.EXPO_PUBLIC_SHOW_ONBOARDING === '1';

export function loadFinished(): boolean {
  if (ALWAYS_SHOW || !stateFile.exists) return false;
  try {
    return JSON.parse(stateFile.textSync()).finished === true;
  } catch {
    return false;
  }
}

export function saveFinished(finished: boolean) {
  stateFile.write(JSON.stringify({ finished }));
}
