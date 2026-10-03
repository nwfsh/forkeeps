import { Directory, File, Paths } from 'expo-file-system';

import type { Analysis } from '@/lib/server';

export type Photo = {
  id: string;
  uri: string;
  takenAt: number;
  /** What the coach saw when the shutter fired; becomes a training example later. */
  analysis: Analysis | null;
};

const dir = new Directory(Paths.document, 'photos');

function ensureDir() {
  dir.create({ idempotent: true, intermediates: true });
}

/** Moves a freshly captured photo out of the cache into app storage, with a JSON sidecar. */
export function storePhoto(sourceUri: string, analysis: Analysis | null): Photo {
  ensureDir();
  const takenAt = Date.now();
  const id = String(takenAt);
  const image = new File(sourceUri);
  image.moveSync(new File(dir, `${id}.jpg`));
  new File(dir, `${id}.json`).write(JSON.stringify({ takenAt, analysis }));
  return { id, uri: image.uri, takenAt, analysis };
}

/** All stored photos, newest first. */
export function loadPhotos(): Photo[] {
  ensureDir();
  const photos: Photo[] = [];
  for (const item of dir.list()) {
    if (!(item instanceof File) || !item.name.endsWith('.jpg')) continue;
    const id = item.name.slice(0, -'.jpg'.length);
    const sidecar = new File(dir, `${id}.json`);
    let meta: { takenAt?: number; analysis?: Analysis | null } = {};
    try {
      if (sidecar.exists) meta = JSON.parse(sidecar.textSync());
    } catch {
      // A broken sidecar shouldn't hide the photo.
    }
    photos.push({ id, uri: item.uri, takenAt: meta.takenAt ?? Number(id), analysis: meta.analysis ?? null });
  }
  return photos.sort((a, b) => b.takenAt - a.takenAt);
}

export function deletePhoto(id: string) {
  for (const name of [`${id}.jpg`, `${id}.json`]) {
    const file = new File(dir, name);
    if (file.exists) file.delete();
  }
}
