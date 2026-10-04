"""Makeup reminders: compare the lips and cheeks in each frame with a photo of a look the person
likes, and say when one has faded.

Plain rules against the person's own reference photo, kept apart from the taste model: the
model learns which photos someone prefers, while this only checks the makeup is still on.
Colour is measured as how much redder the lips and cheek apples are than the forehead in the same
photo (vision.face_colour), so the room's light mostly cancels out.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import choices_db

FOLDER = Path(__file__).resolve().parent / "preferences" / "makeup"
# A frame's colour below this share of the reference's counts as faded. Lips are mentioned as soon
# as they fade noticeably; cheeks only once the blush is all but gone, since blush reads softer
# and patchier on camera and a reminder for a little fading is nagging.
KEEP = {"lip_colour": 0.6, "blush": 0.25}
# A reference with less colour than this on the cheeks has no blush to keep, so cheeks aren't checked.
MIN_BLUSH = 0.015
# Colour reads unreliably on a turned face (one cheek goes into shadow), so only faces within
# this many degrees of front-on are checked, as for vision's face shape.
MAX_TURN = 30

CHECKS = (
    # (code, measure in face_colour, voice clip, message)
    ("lips_faded", "lip_colour", "reapply_lips", "Your lip colour has faded: time to reapply"),
    ("blush_faded", "blush", "reapply_blush", "Your cheeks have lost their colour: add some blush"),
)


def _path(person: str) -> Path:
    return FOLDER / f"{choices_db.person_key(person)}.json"


def reference_from(result: dict) -> dict:
    """The look in an analysed photo, to keep as the reference. Raises ValueError when the photo
    can't be read for it."""
    faces = result["faces"]
    if len(faces) != 1:
        raise ValueError("Use a photo with just your face in it")
    # The colours are read at face points, so the face has to be found whole and uncovered.
    flags = result.get("red_flags") or []
    if flags:
        reason = {"face_covered": "something is in front of your face",
                  "face_cut_off": "your face is cut off by the edge",
                  "face_too_small": "your face is too small in it"}.get(flags[0], "your face isn't clear")
        raise ValueError(f"Use another photo: {reason}")
    yaw = (faces[0].get("pose") or {}).get("yaw")
    if yaw is not None and abs(yaw) > MAX_TURN:
        raise ValueError("Use a more front-on photo, so both cheeks are in view")
    colour = faces[0].get("colour") or {}
    if "lip_colour" not in colour:
        raise ValueError("Couldn't read your lips and cheeks; try a clearer, front-on photo")
    regions = colour["regions"]
    return {
        "lip_colour": colour["lip_colour"],
        "blush": colour["blush"],
        "lips_hex": regions["lips"]["hex"],
        "cheeks_hex": regions["cheek_apple"]["hex"],
        "skin_hex": regions["forehead"]["hex"],
        "checks_blush": colour["blush"] >= MIN_BLUSH,
    }


def save(person: str, reference: dict) -> dict:
    FOLDER.mkdir(parents=True, exist_ok=True)
    saved = {**reference, "person": person,
             "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    _path(person).write_text(json.dumps(saved, indent=1))
    return saved


def load(person: str) -> Optional[dict]:
    path = _path(person)
    return json.loads(path.read_text()) if path.exists() else None


def clear(person: str) -> None:
    _path(person).unlink(missing_ok=True)


def check(result: dict, reference: Optional[dict]) -> list[dict]:
    """[{"code", "clip", "message", "strength"}] for each part that has faded, where strength is
    the frame's colour as a share of the reference's. Empty when there's no reference or the frame
    can't be judged (no single clear face, or turned too far)."""
    if not reference or result.get("red_flags") or len(result["faces"]) != 1:
        return []
    face = result["faces"][0]
    colour = face.get("colour") or {}
    turn = (face.get("pose") or {}).get("yaw")
    if turn is not None and abs(turn) > MAX_TURN:
        return []
    faded = []
    for code, measure, clip, message in CHECKS:
        if measure == "blush" and not reference.get("checks_blush"):
            continue
        target, now = reference.get(measure), colour.get(measure)
        if not target or target <= 0 or now is None:
            continue
        strength = now / target
        if strength < KEEP[measure]:
            faded.append({"code": code, "clip": clip, "message": message,
                          "strength": round(max(0.0, strength), 2)})
    return faded
