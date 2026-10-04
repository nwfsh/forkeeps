import { File, Paths } from 'expo-file-system';

/** Onboarding's results: what the taste model trained from the swipes learned. */

/** One row of Ranker.priorities(). */
export type Priority = {
  feature: string;
  label: string;
  /** Positive: they pick more of it. Negative: less. */
  weight: number;
  /** Share of total influence, 0–1. */
  share: number;
  /** The preference in words, e.g. "Chin down"; shown instead of label plus more/less. */
  prefers?: string;
};

/** Matches the server's thresholds (ranker.CLEAR and ranker.LIKELY). */
export type Confidence = 'clear' | 'likely' | 'unclear';

export function confidenceLevel(confidence: number): Confidence {
  return confidence >= 0.95 ? 'clear' : confidence >= 0.7 ? 'likely' : 'unclear';
}

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
