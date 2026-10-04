import { useRef, useState } from 'react';

import type { Analysis, MakeupTip } from '@/lib/server';

/** Lips or cheeks have to look faded this long before the coach says so: one odd frame doesn't. */
const HOLD_MS = 1500;
/** A part counts as fixed once it hasn't looked faded for this long, so one good frame doesn't clear it. */
const CLEAR_MS = 1500;

/**
 * The makeup reminder to show, if any (server/makeup.py checks each frame against the person's
 * makeup look). Call `onFrame` with every analysis. Once lips or cheeks have looked faded for
 * HOLD_MS the reminder stays up until they're fixed; lips come first, as the most noticeable.
 */
export function useMakeupReminder() {
  const [tip, setTip] = useState<MakeupTip | null>(null);
  // When each part started looking faded, when it last did, and how it was described, by code.
  const fadedSince = useRef(new Map<string, number>());
  const lastFaded = useRef(new Map<string, MakeupTip & { at: number }>());

  function onFrame(frame: Analysis) {
    const now = Date.now();
    for (const t of frame.makeup ?? []) {
      if (!fadedSince.current.has(t.code)) fadedSince.current.set(t.code, now);
      lastFaded.current.set(t.code, { ...t, at: now });
    }
    for (const [code, last] of lastFaded.current) {
      if (now - last.at > CLEAR_MS) {
        fadedSince.current.delete(code);
        lastFaded.current.delete(code);
      }
    }
    const showing = (['lips_faded', 'blush_faded'] as const)
      .map((code) => ({ since: fadedSince.current.get(code), last: lastFaded.current.get(code) }))
      .find(({ since, last }) => since !== undefined && last && now - since >= HOLD_MS)?.last;
    setTip((current) =>
      current?.code === showing?.code ? current : showing ? { ...showing } : null,
    );
  }

  return { tip, onFrame };
}
