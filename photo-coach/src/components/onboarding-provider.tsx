import { createContext, useContext, useState, type ReactNode } from 'react';

import { loadFinished, saveFinished, type Pick } from '@/lib/onboarding';

type OnboardingContextValue = {
  /** Whether onboarding is done; the root layout shows the camera tabs once it is. */
  finished: boolean;
  /** Choices made on the "choose between pics" screen, oldest first. */
  picks: Pick[];
  pick: (winner: string, loser: string) => void;
  finish: () => void;
  /** Shows onboarding again from the start, e.g. from "Replay intro". */
  restart: () => void;
};

const OnboardingContext = createContext<OnboardingContextValue | null>(null);

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const [finished, setFinished] = useState(loadFinished);
  const [picks, setPicks] = useState<Pick[]>([]);

  function pick(winner: string, loser: string) {
    // TODO: send each pick to the server so the ranker can learn from it.
    setPicks((list) => [...list, { winner, loser }]);
  }

  function finish() {
    saveFinished(true);
    setFinished(true);
  }

  function restart() {
    saveFinished(false);
    setPicks([]);
    // The root layout's guards then swap the camera tabs for onboarding.
    setFinished(false);
  }

  return (
    <OnboardingContext.Provider value={{ finished, picks, pick, finish, restart }}>
      {children}
    </OnboardingContext.Provider>
  );
}

export function useOnboarding() {
  const value = useContext(OnboardingContext);
  if (!value) throw new Error('useOnboarding must be used inside OnboardingProvider');
  return value;
}
