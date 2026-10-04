"""Judge a camera frame as a photo: how good it is, and whether it's perfect enough to take.

The app's auto-capture fires when frames are perfect, and its bursts keep the best-scoring shot.
With a trained taste model (preferences/weights/<person>.json, from retrain.py or compare.py)
the score is that model's chance the photo beats an average one of theirs; without one it
falls back to simple rules, so auto-capture works before anyone has trained anything.
"""
import json
from pathlib import Path
from typing import Optional

import numpy as np

import choices_db
from ranker import photo_features
from score import LIKELY_PICK, WEIGHTS_FOLDER, win_chance

# A perfect shot needs eyes at least this open (1 - the blink score); a blink scores about 0.1.
MIN_EYES_OPEN = 0.7
# With a model, a perfect shot is one it thinks is a likely pick.
PERFECT_SCORE = LIKELY_PICK
# Taste instructions: what to say to move each feature up or down, as (clip, message). Only
# features the person in the photo controls; the first of each pair raises the feature.
INSTRUCTIONS = {
    "eye_contact": (("look_at_lens", "Look straight into the lens"), ("look_away", "Look just past the camera")),
    "smile": (("smile_more", "Smile a little"), ("relax_smile", "Soften your smile")),
    "teeth_shown": (("show_teeth", "Smile with a little teeth"), ("close_lips", "Smile with your lips closed")),
    "chin_up": (("chin_up", "Tilt your chin up a little"), ("chin_down", "Tilt your chin down a little")),
    # Said from the person's own point of view, so it's right whether they're watching a mirrored
    # selfie preview or someone else is filming. Showing the left cheek means turning to the right.
    "left_side": (("turn_left_side", "Turn your head a little to your right"),
                  ("turn_right_side", "Turn your head a little to your left")),
}
# Curved features: an angle and its squared copy score together, so a best angle can sit between.
CURVED = {"chin_up": "chin_up_curve", "left_side": "left_side_curve"}
# Values each feature can really take: scores are 0-1, and head angles are coached within 45°
# (half a quarter turn) of facing the camera.
POSSIBLE = {"eye_contact": (0.0, 1.0), "smile": (0.0, 1.0), "teeth_shown": (0.0, 1.0),
            "chin_up": (-0.5, 0.5), "left_side": (-0.5, 0.5)}
# Where to look for the best value of a feature: this many of its spreads either side of its
# average over the person's training photos (within POSSIBLE), in TARGET_STEPS steps. One spread
# keeps a "the more the better" preference to what their kept photos actually showed; two sent
# people chasing extremes (a chin 33° down) that no photo they liked had.
TARGET_RANGE = 1.0
TARGET_STEPS = 41
# Only coach a change worth at least this much (in the model's log-odds), and only when the
# best value is at least this many spreads away, so tiny wobbles don't trigger a new line.
MIN_GAIN = 0.3
MIN_MOVE = 0.5
# Without one, the rules score must reach this. Our 108 photos score 0.46-0.80 (median 0.76),
# so this passes roughly the better two-thirds rather than everything without a tip.
RULES_PERFECT_SCORE = 0.65
# Without a model: each tip on screen costs this much of the rule-based score.
WARNING_COST = 0.15

_models: dict[str, tuple[bytes, dict]] = {}


def load_model(person: Optional[str]) -> Optional[dict]:
    """Someone's saved weights, parsed again only when the file's contents change. None if they
    have none.

    Compared by contents, not modified time: a retrain can rewrite the file within the same clock
    tick (Windows often reports the same time), and the old model would then be kept. The file is
    a few KB, so reading it for every frame costs nothing noticeable.
    """
    if not person:
        return None
    path: Path = WEIGHTS_FOLDER / f"{choices_db.person_key(person)}.json"
    if not path.exists():
        return None
    data = path.read_bytes()
    cached = _models.get(path.name)
    if not cached or cached[0] != data:
        _models[path.name] = cached = (data, json.loads(data))
    return cached[1]


def rules_score(result: dict) -> float:
    """0-1 from eyes open, eye contact, focus and framing, less a bit for every tip."""
    f = photo_features(result)
    parts = [f[name] for name in ("eyes_open", "eye_contact", "sharpness", "face_in_frame") if f[name] is not None]
    base = sum(parts) / len(parts) if parts else 0.0
    return max(0.0, min(1.0, base - WARNING_COST * len(result["warnings"])))


def feature_score(name: str, value: float, model: dict) -> float:
    """One feature's part of the model's log-odds, including its squared copy if it has one."""
    weights, mean, std = model["weights"], model["mean"], model["std"]
    total = weights.get(name, 0.0) * (value - mean[name]) / std[name] if name in weights else 0.0
    curve = CURVED.get(name)
    if curve in weights:
        total += weights[curve] * (value ** 2 - mean[curve]) / std[curve]
    return total


def instruction(features: dict, model: dict) -> Optional[dict]:
    """The one change the person can make that the model thinks would help most, or None.

    For each feature in INSTRUCTIONS the model learns from, finds the value it scores highest
    across the range of the person's own photos (so a best angle in between counts), and how
    much moving there would add. {"code", "clip", "message", "gain"} for the biggest gain.
    """
    best = None
    for name, (raise_it, lower_it) in INSTRUCTIONS.items():
        value = features.get(name)
        if value is None or name not in model.get("mean", {}) or (
                name not in model["weights"] and CURVED.get(name) not in model["weights"]):
            continue
        centre, spread = model["mean"][name], model["std"][name]
        low, high = POSSIBLE[name]
        candidates = np.linspace(max(low, centre - TARGET_RANGE * spread),
                                 min(high, centre + TARGET_RANGE * spread), TARGET_STEPS)
        target = max(candidates, key=lambda v: feature_score(name, v, model))
        gain = feature_score(name, target, model) - feature_score(name, value, model)
        if gain < MIN_GAIN or abs(target - value) < MIN_MOVE * spread:
            continue
        if best is None or gain > best[0]:
            clip, message = raise_it if target > value else lower_it
            best = (gain, {"code": clip, "clip": clip, "message": message, "gain": round(float(gain), 2)})
    return best[1] if best else None


def judge(result: dict, model: Optional[dict]) -> dict:
    """{"score", "scored_by", "perfect", "blockers", "instruction"}: blockers say what stops it
    being perfect; instruction is the taste change to coach, or None."""
    blockers = list(result.get("red_flags", [])) + [w["code"] for w in result["warnings"]]
    tip = None
    if model:
        features = photo_features(result)
        score, scored_by = win_chance(features, model), "model"
        tip = instruction(features, model)
    else:
        score, scored_by = rules_score(result), "rules"
    faces = result["faces"]
    eyes = faces[0].get("measurements", {}).get("eye_openness") if len(faces) == 1 else None
    if eyes is not None and eyes < MIN_EYES_OPEN:
        blockers.append("eyes_closed")
    if score < (PERFECT_SCORE if scored_by == "model" else RULES_PERFECT_SCORE):
        blockers.append("low_score")
    return {"score": round(score, 3), "scored_by": scored_by, "perfect": not blockers, "blockers": blockers,
            "instruction": tip}
