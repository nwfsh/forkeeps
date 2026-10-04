import { createContext, useContext, useState, type ReactNode } from 'react';

import { loadFinished, saveFinished } from '@/lib/onboarding';
import type { Analysis, RetrainResult } from '@/lib/server';

/** A frame from the onboarding recording, picked to swipe on. */
export type Snapshot = { id: string; uri: string; analysis: Analysis };

type OnboardingContextValue = {
  /** Whether onboarding is done; the root layout shows the camera tabs once it is. */
  finished: boolean;
  /** The recording's frames picked for swiping, most typical first. */
  snapshots: Snapshot[];
  setSnapshots: (snapshots: Snapshot[]) => void;
  /** The taste model trained from the swipes, for the results screen. */
  results: RetrainResult | null;
  setResults: (results: RetrainResult) => void;
  finish: () => void;
  /**
   * Shows onboarding again from the start, e.g. from "Replay intro". With `preview`, every page
   * gets a Skip button, for looking over the design.
   */
  restart: (preview?: boolean) => void;
  /** Whether this run of onboarding is a preview with Skip buttons. */
  preview: boolean;
};

const OnboardingContext = createContext<OnboardingContextValue | null>(null);

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const [finished, setFinished] = useState(loadFinished);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [results, setResults] = useState<RetrainResult | null>(null);
  const [preview, setPreview] = useState(false);

  function finish() {
    setPreview(false);
    saveFinished(true);
    setFinished(true);
  }

  function restart(preview = false) {
    setPreview(preview);
    saveFinished(false);
    setSnapshots([]);
    setResults(null);
    // The root layout's guards then swap the camera tabs for onboarding.
    setFinished(false);
  }

  return (
    <OnboardingContext.Provider
      value={{
        finished,
        snapshots,
        setSnapshots,
        results,
        setResults,
        finish,
        restart,
        preview,
      }}>
      {children}
    </OnboardingContext.Provider>
  );
}

export function useOnboarding() {
  const value = useContext(OnboardingContext);
  if (!value) throw new Error('useOnboarding must be used inside OnboardingProvider');
  return value;
}
