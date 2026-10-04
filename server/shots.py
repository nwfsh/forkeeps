"""Judge a camera frame as a photo: how good it is, and whether it's perfect enough to take.

The app's auto-capture fires when frames are perfect, and its bursts keep the best-scoring shot.
With a trained taste model (preferences/weights/<person>.json, from retrain.py or compare.py)
the score is that model's chance the photo beats an average one of theirs; without one it
falls back to simple rules, so auto-capture works before anyone has trained anything.
"""
import json
from pathlib import Path
from typing import Optional

import choices_db
from ranker import photo_features
from score import LIKELY_PICK, WEIGHTS_FOLDER, win_chance

# A perfect shot needs eyes at least this open (1 - the blink score); a blink scores about 0.1.
MIN_EYES_OPEN = 0.7
# With a model, a perfect shot is one it thinks is a likely pick.
PERFECT_SCORE = LIKELY_PICK
# Without one, the rules score must reach this. Our 108 photos score 0.46-0.80 (median 0.76),
# so this passes roughly the better two-thirds rather than everything without a tip.
RULES_PERFECT_SCORE = 0.65
# Without a model: each tip on screen costs this much of the rule-based score.
WARNING_COST = 0.15

_models: dict[str, tuple[float, dict]] = {}


def load_model(person: Optional[str]) -> Optional[dict]:
    """Someone's saved weights, re-read only when the file changes. None if they have none."""
    if not person:
        return None
    path: Path = WEIGHTS_FOLDER / f"{choices_db.person_key(person)}.json"
    if not path.exists():
        return None
    mtime = path.stat().st_mtime
    cached = _models.get(path.name)
    if not cached or cached[0] != mtime:
        _models[path.name] = cached = (mtime, json.loads(path.read_text()))
    return cached[1]


def rules_score(result: dict) -> float:
    """0-1 from eyes open, eye contact, focus and framing, less a bit for every tip."""
    f = photo_features(result)
    parts = [f[name] for name in ("eyes_open", "eye_contact", "sharpness", "face_in_frame") if f[name] is not None]
    base = sum(parts) / len(parts) if parts else 0.0
    return max(0.0, min(1.0, base - WARNING_COST * len(result["warnings"])))


def judge(result: dict, model: Optional[dict]) -> dict:
    """{"score", "scored_by", "perfect", "blockers"}: blockers say what stops it being perfect."""
    blockers = list(result.get("red_flags", [])) + [w["code"] for w in result["warnings"]]
    if model:
        score, scored_by = win_chance(photo_features(result), model), "model"
    else:
        score, scored_by = rules_score(result), "rules"
    faces = result["faces"]
    eyes = faces[0].get("measurements", {}).get("eye_openness") if len(faces) == 1 else None
    if eyes is not None and eyes < MIN_EYES_OPEN:
        blockers.append("eyes_closed")
    if score < (PERFECT_SCORE if scored_by == "model" else RULES_PERFECT_SCORE):
        blockers.append("low_score")
    return {"score": round(score, 3), "scored_by": scored_by, "perfect": not blockers, "blockers": blockers}
