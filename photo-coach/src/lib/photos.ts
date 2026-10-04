import { Directory, File, Paths } from 'expo-file-system';

import type { Analysis } from '@/lib/server';

export type Photo = {
  id: string;
  uri: string;
  takenAt: number;
  /** What the coach saw when the shutter fired; becomes a training example later. */
  analysis: Analysis | null;
  /** Set once the photo is kept in review. Removed photos are deleted, so never have one. */
  kept: boolean;
  /** Shared by every shot of one burst. */
  burst?: string;
  /**
   * A burst shot that wasn't picked as the best. It waits in review instead of showing in the
   * photo grid, and shows up there once kept.
   */
  alternate?: boolean;
};

export type BurstInfo = Pick<Photo, 'burst' | 'alternate'>;

type Sidecar = { takenAt?: number; analysis?: Analysis | null; kept?: boolean } & BurstInfo;

const dir = new Directory(Paths.document, 'photos');

function ensureDir() {
  dir.create({ idempotent: true, intermediates: true });
}

/** Moves a freshly captured photo out of the cache into app storage, with a JSON sidecar. */
export function storePhoto(sourceUri: string, analysis: Analysis | null, burstInfo: BurstInfo = {}): Photo {
  ensureDir();
  const takenAt = Date.now();
  // Burst shots are saved within the same millisecond, so the time alone can repeat.
  let id = String(takenAt);
  for (let n = 1; new File(dir, `${id}.jpg`).exists; n++) id = `${takenAt}-${n}`;
  const image = new File(sourceUri);
  image.moveSync(new File(dir, `${id}.jpg`));
  new File(dir, `${id}.json`).write(JSON.stringify({ takenAt, analysis, ...burstInfo }));
  return { id, uri: image.uri, takenAt, analysis, kept: false, ...burstInfo };
}

function readSidecar(id: string): Sidecar {
  const sidecar = new File(dir, `${id}.json`);
  try {
    if (sidecar.exists) return JSON.parse(sidecar.textSync());
  } catch {
    // A broken sidecar shouldn't hide the photo.
  }
  return {};
}

/** Remembers that the photo was kept in review, so it isn't shown for review again. */
export function markKept(id: string) {
  ensureDir();
  new File(dir, `${id}.json`).write(JSON.stringify({ ...readSidecar(id), kept: true }));
}

/** All stored photos, newest first. */
export function loadPhotos(): Photo[] {
  ensureDir();
  const photos: Photo[] = [];
  for (const item of dir.list()) {
    if (!(item instanceof File) || !item.name.endsWith('.jpg')) continue;
    const id = item.name.slice(0, -'.jpg'.length);
    const meta = readSidecar(id);
    photos.push({
      id,
      uri: item.uri,
      takenAt: meta.takenAt ?? parseInt(id, 10),
      analysis: meta.analysis ?? null,
      kept: meta.kept === true,
      burst: meta.burst,
      alternate: meta.alternate,
    });
  }
  return photos.sort((a, b) => b.takenAt - a.takenAt);
}

export function deletePhoto(id: string) {
  for (const name of [`${id}.jpg`, `${id}.json`]) {
    const file = new File(dir, name);
    if (file.exists) file.delete();
  }
}
