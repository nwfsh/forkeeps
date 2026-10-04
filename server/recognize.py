"""Find known people in group photos.

Run from server/:
  python recognize.py enroll                learn each person from data/training-recognition/<name>/
  python recognize.py find NAME [FOLDER]    list the photos in FOLDER (default data/group-photos) with NAME in them

NAME can be `everyone` to look for all the saved people in one pass.
`find` also saves a copy of every photo with its faces boxed and named to data/found/NAME/.
"""
import sys
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from insightface.app import FaceAnalysis
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

DATA = Path(__file__).resolve().parent.parent / "data"
PEOPLE_FOLDER = DATA / "training-recognition"
GROUP_FOLDER = DATA / "group-photos"
FOUND_FOLDER = DATA / "found"
# One averaged face vector per person. Kept under data/ so it stays out of git.
REFERENCES_PATH = DATA / "face-references.npz"
PHOTO_TYPES = {".jpg", ".jpeg", ".png", ".heic", ".heif"}
# Given to `find` in place of a name to look for all the saved people.
EVERYONE = "everyone"

# The detector shrinks photos to fit a square this size. Group photos need a big one so
# small faces survive; a face filling the frame of a solo photo is missed unless it's small.
GROUP_DETECT_SIZE = 1280
SOLO_DETECT_SIZE = 640
# Cosine similarity (-1 to 1) a face needs with a person's reference to be given their name.
# On our 153 group photos the wrong person never scored above 0.2, and the lowest score
# for the right person (a full side profile) was 0.37.
MATCH_THRESHOLD = 0.3
# Solo photos whose face is less similar than this to the person's average are left out
# of their reference: usually someone else's face was the biggest in the photo.
ENROLL_OUTLIER = 0.3
PREVIEW_WIDTH = 1600
MATCH_COLOUR = (0, 255, 0)
OTHER_COLOUR = (160, 160, 160)

register_heif_opener()


def load_model(detect_size: int) -> FaceAnalysis:
    """The face detector and embedder. Has no limit on the number of faces per photo."""
    model = FaceAnalysis(name="buffalo_l", allowed_modules=["detection", "recognition"],
                         providers=["CPUExecutionProvider"])
    model.prepare(ctx_id=-1, det_size=(detect_size, detect_size))
    return model


def load_image(path: Path) -> np.ndarray:
    """Read a JPEG, PNG or HEIC photo as an RGB array, honouring EXIF orientation."""
    with Image.open(path) as image:
        return np.asarray(ImageOps.exif_transpose(image).convert("RGB"))


def photos_in(folder: Path) -> list[Path]:
    """Every photo in the folder and its subfolders."""
    return sorted(p for p in folder.rglob("*") if p.suffix.lower() in PHOTO_TYPES)


def find_faces(model: FaceAnalysis, rgb: np.ndarray) -> list[dict]:
    """Every face in the photo, with its box as fractions of the image and its unit-length vector."""
    height, width = rgb.shape[:2]
    found = []
    for face in model.get(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)):
        x1, y1, x2, y2 = face.bbox.tolist()
        found.append({
            "bbox": {"x": round(x1 / width, 4), "y": round(y1 / height, 4),
                     "w": round((x2 - x1) / width, 4), "h": round((y2 - y1) / height, 4)},
            "vector": face.normed_embedding,
        })
    return found


def average(vectors: list[np.ndarray]) -> np.ndarray:
    """The unit-length mean of some unit-length vectors."""
    mean = np.mean(vectors, axis=0)
    return mean / np.linalg.norm(mean)


def enroll() -> None:
    """Average each person's solo photos into one reference vector and save them all."""
    model = load_model(SOLO_DETECT_SIZE)
    references = {}
    for folder in sorted(p for p in PEOPLE_FOLDER.iterdir() if p.is_dir()):
        paths = photos_in(folder)
        vectors = []
        for path in paths:
            faces = find_faces(model, load_image(path))
            if faces:
                # The person the photo is of is taken to be the biggest face in it.
                vectors.append(max(faces, key=lambda f: f["bbox"]["w"] * f["bbox"]["h"])["vector"])
        if not vectors:
            print(f"{folder.name:10} no faces found in {len(paths)} photos, skipped")
            continue
        rough = average(vectors)
        kept = [v for v in vectors if float(v @ rough) >= ENROLL_OUTLIER]
        references[folder.name] = average(kept)
        print(f"{folder.name:10} {len(kept)} of {len(paths)} photos used "
              f"({len(paths) - len(vectors)} with no face, {len(vectors) - len(kept)} left out as someone else)")
    np.savez(REFERENCES_PATH, **references)
    print(f"saved {len(references)} people to {REFERENCES_PATH}")


def load_references() -> dict:
    if not REFERENCES_PATH.exists():
        sys.exit("no saved people yet: run `python recognize.py enroll` first")
    with np.load(REFERENCES_PATH) as saved:
        return {name: saved[name] for name in saved.files}


def name_faces(faces: list[dict], references: dict) -> None:
    """Give each face a "name" (or None) and its "score", the similarity to that person.

    Best matches are handed out first and each person is used once per photo, so two
    faces can't both be the same person.
    """
    names = list(references)
    for face in faces:
        face["name"], face["score"] = None, 0.0
    if not faces:
        return
    scores = np.array([[float(face["vector"] @ references[name]) for name in names] for face in faces])
    for _ in range(min(len(faces), len(names))):
        i, j = np.unravel_index(np.argmax(scores), scores.shape)
        if scores[i, j] < MATCH_THRESHOLD:
            break
        faces[i]["name"], faces[i]["score"] = names[j], round(float(scores[i, j]), 2)
        scores[i, :] = -1
        scores[:, j] = -1


def is_wanted(face: dict, wanted: Optional[str]) -> bool:
    """Whether the face was named as the wanted person, or as anyone when wanted is None."""
    return face["name"] is not None and wanted in (None, face["name"])


def save_preview(rgb: np.ndarray, faces: list[dict], wanted: Optional[str], path: Path) -> None:
    """Save a shrunk copy of the photo with every face boxed, the wanted people in green."""
    scale = PREVIEW_WIDTH / rgb.shape[1]
    preview = cv2.resize(rgb, (PREVIEW_WIDTH, round(rgb.shape[0] * scale)))
    height, width = preview.shape[:2]
    for face in faces:
        b = face["bbox"]
        top_left = (int(b["x"] * width), int(b["y"] * height))
        bottom_right = (int((b["x"] + b["w"]) * width), int((b["y"] + b["h"]) * height))
        colour = MATCH_COLOUR if is_wanted(face, wanted) else OTHER_COLOUR
        label = f"{face['name']} {face['score']}" if face["name"] else "?"
        cv2.rectangle(preview, top_left, bottom_right, colour, 3)
        cv2.putText(preview, label, (top_left[0], max(20, top_left[1] - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, colour, 2)
    cv2.imwrite(str(path), cv2.cvtColor(preview, cv2.COLOR_RGB2BGR))


def find(wanted: Optional[str], folder: Path) -> None:
    """Print who of the wanted people (everyone saved, when None) is in each photo in the
    folder, and save labelled copies."""
    references = load_references()
    if wanted is not None and wanted not in references:
        sys.exit(f"don't know {wanted!r}: saved people are {', '.join(references)}")
    model = load_model(GROUP_DETECT_SIZE)
    out = FOUND_FOLDER / (wanted or EVERYONE)
    out.mkdir(parents=True, exist_ok=True)
    paths = photos_in(folder)
    hits = {name: 0 for name in references if wanted in (None, name)}
    for path in paths:
        rgb = load_image(path)
        faces = find_faces(model, rgb)
        name_faces(faces, references)
        matches = sorted((f for f in faces if is_wanted(f, wanted)), key=lambda f: f["name"])
        for face in matches:
            hits[face["name"]] += 1
        found = ", ".join(f"{f['name']} {f['score']}" for f in matches) or "-"
        if wanted and matches:
            found += f"  {matches[0]['bbox']}"
        print(f"{path.name:22} {len(faces):2} faces  {found}", flush=True)
        save_preview(rgb, faces, wanted, out / f"{path.stem}.jpg")
    print()
    for name, count in hits.items():
        print(f"{name} is in {count} of {len(paths)} photos")
    print(f"labelled copies are in {out}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["enroll"]:
        enroll()
    elif len(args) in (2, 3) and args[0] == "find":
        find(None if args[1] == EVERYONE else args[1], Path(args[2]) if len(args) == 3 else GROUP_FOLDER)
    else:
        sys.exit(__doc__)
