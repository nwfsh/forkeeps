import { shrink } from '@/hooks/use-frame-analysis';
import { analyzeFrame, type Analysis } from '@/lib/server';

/** Shots per burst: enough to catch one without a blink, few enough to score in a couple of seconds. */
export const BURST_SIZE = 4;

export type BurstShot = { uri: string; analysis: Analysis | null };

/**
 * Has the server judge each shot of a burst (a small copy, like a live frame) and returns
 * them best first. A shot the server couldn't judge goes last; if none could be judged,
 * the order is the order they were taken.
 */
export async function rankBurst(uris: string[]): Promise<BurstShot[]> {
  const shots: BurstShot[] = [];
  // One at a time: the server analyses one image at a time anyway.
  for (const uri of uris) {
    try {
      shots.push({ uri, analysis: await analyzeFrame(await shrink(uri)) });
    } catch {
      shots.push({ uri, analysis: null });
    }
  }
  const score = (shot: BurstShot) => shot.analysis?.shot?.score ?? -1;
  // Array.prototype.sort is stable, so equal scores keep the order they were taken in.
  return [...shots].sort((a, b) => score(b) - score(a));
}
