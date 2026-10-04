"""Who the photo is of, when there's more than one person in it.

The app teaches the server a person's face from the snapshots of their onboarding recording
(enroll). In a frame with several faces, the one that matches is the subject: the analysis is
narrowed to that face and their body, so framing, the taste model and makeup are judged on them
and other people in the shot are fine. Only when no face matches does "several_people" stand.

Face vectors come from insightface (recognize.py). They're biometric, so they're kept in
preferences/faces/, which git ignores.
"""
from pathlib import Path
from typing import Optional

import numpy as np

import choices_db
import recognize
import vision

FOLDER = Path(__file__).resolve().parent / "preferences" / "faces"
# Measured faces and insightface's faces are matched by how much their boxes overlap.
SAME_FACE = 0.3
# A body counts as the subject's when its head overlaps their face at least this much.
SAME_HEAD = 0.1

_model = None


def model():
    """insightface, loaded the first time it's needed (it takes a few seconds)."""
    global _model
    if _model is None:
        _model = recognize.load_model(recognize.SOLO_DETECT_SIZE)
    return _model


def _path(person: str) -> Path:
    return FOLDER / f"{choices_db.person_key(person)}.npy"


def load(person: str) -> Optional[np.ndarray]:
    path = _path(person)
    return np.load(path) if path.exists() else None


def enroll(person: str, images: list[np.ndarray]) -> int:
    """Learn `person`'s face from photos of them (the biggest face in each), and return how many
    photos were used. Raises ValueError when no face was found in any."""
    vectors = []
    for rgb in images:
        faces = recognize.find_faces(model(), rgb)
        if faces:
            vectors.append(max(faces, key=lambda f: f["bbox"]["w"] * f["bbox"]["h"])["vector"])
    if not vectors:
        raise ValueError("No face found in those photos")
    rough = recognize.average(vectors)
    kept = [v for v in vectors if float(v @ rough) >= recognize.ENROLL_OUTLIER] or vectors
    FOLDER.mkdir(parents=True, exist_ok=True)
    np.save(_path(person), recognize.average(kept))
    return len(kept)


def _box(b: dict) -> tuple:
    return (b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"])


def find(rgb: np.ndarray, faces: list[dict], reference: np.ndarray) -> Optional[int]:
    """Which of the measured faces is the person, by their face vector, or None."""
    best, best_score = None, recognize.MATCH_THRESHOLD
    for known in recognize.find_faces(model(), rgb):
        score = float(known["vector"] @ reference)
        if score < best_score:
            continue
        overlaps = [vision.overlap(_box(f["bbox"]), _box(known["bbox"])) for f in faces]
        i = int(np.argmax(overlaps))
        if overlaps[i] >= SAME_FACE:
            best, best_score = i, score
    return best


def focus(result: dict, rgb: np.ndarray, person: Optional[str]) -> dict:
    """The analysis narrowed to `person` when there are several faces and one is theirs.

    Adds "subject": "found" (narrowed; the rest are in "others"), "unknown" (several faces, none
    theirs), "not_enrolled" (several faces, their face hasn't been learned) or None (one face or
    none, nothing to decide). A crowd is more than one face, or more than one body (someone with
    their back turned has no face to see).
    """
    faces = result["faces"]
    crowded = len(faces) > 1 or len(result["people"]) > 1
    if not crowded or not faces or not person:
        return {**result, "subject": None}
    reference = load(person)
    if reference is None:
        return {**result, "subject": "not_enrolled"}
    i = find(rgb, faces, reference)
    if i is None:
        return {**result, "subject": "unknown"}
    face = {**faces[i], "name": person}
    box = _box(face["bbox"])
    people = [p for p in result["people"] if vision.overlap(vision.head_box(p["points"]), box) >= SAME_HEAD]
    people = sorted(people, key=lambda p: -vision.overlap(vision.head_box(p["points"]), box))[:1]
    return {
        **result,
        "faces": [face],
        "people": people,
        "others": [{"bbox": f["bbox"], "name": f.get("name")} for j, f in enumerate(faces) if j != i],
        "warnings": vision.framing_warnings([face], people),
        "red_flags": vision.red_flags([face], people),
        "subject": "found",
    }
