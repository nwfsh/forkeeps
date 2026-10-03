import { createContext, useContext, useState, type ReactNode } from 'react';

import { deletePhoto, loadPhotos, storePhoto, type Photo } from '@/lib/photos';
import type { Analysis } from '@/lib/server';

type PhotosContextValue = {
  /** Newest first. */
  photos: Photo[];
  add: (uri: string, analysis: Analysis | null) => Photo;
  remove: (id: string) => void;
};

const PhotosContext = createContext<PhotosContextValue | null>(null);

export function PhotosProvider({ children }: { children: ReactNode }) {
  const [photos, setPhotos] = useState<Photo[]>(loadPhotos);

  function add(uri: string, analysis: Analysis | null) {
    const photo = storePhoto(uri, analysis);
    setPhotos((list) => [photo, ...list]);
    return photo;
  }

  function remove(id: string) {
    deletePhoto(id);
    setPhotos((list) => list.filter((p) => p.id !== id));
  }

  return <PhotosContext.Provider value={{ photos, add, remove }}>{children}</PhotosContext.Provider>;
}

export function usePhotos() {
  const value = useContext(PhotosContext);
  if (!value) throw new Error('usePhotos must be used inside PhotosProvider');
  return value;
}
