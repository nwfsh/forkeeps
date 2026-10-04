"""Learn which photo features someone prioritises from "pick the better photo" choices.

Each photo becomes a row of features (higher always means "more of" the named thing).
Every choice says the winner's features beat the loser's, so a logistic regression on
feature differences (a Bradley-Terry model) learns one weight per feature: how much
more of that feature makes a photo more likely to win.
"""
import math
import random
from typing import Optional

import re

import numpy as np
from sklearn.linear_model import LogisticRegression

from vision import EXPRESSION_REGIONS, EXPRESSIONS

# Feature name -> what it means, worded for the "what you prioritise" ranking.
# Face size and how much of the body is in frame are left out on purpose: they mostly say how
# far away the photographer stood, not anything about the person they would like or dislike.
FEATURES = {
    "eyes_open": "Eyes open",
    "eye_contact": "Looking at the camera",
    "smile": "Smiling",
    "goofy": "Goofy face",
    "head_straight": "Head held straight",
    "chin_level": "Chin level",
    "sharpness": "Sharp focus",
    "face_in_frame": "Face not cut off",
    "clean_crop": "Frame not cutting at a joint",
    "looking_room": "Space in the direction you look",
    "body_turned": "Body angled to the camera",
    "facing_camera": "Facing the camera",
    "upright": "Head over shoulders, not slouching",
    "long_neck": "Shoulders relaxed down",
    "arms_away": "Arms held away from the body",
    "hand_raised": "A hand raised to the hair or head",
    "left_side": "Left side of the face toward the camera",
    "chin_up": "Chin up",
}



def expression_region(name: str) -> str:
    return next(region for prefix, region in EXPRESSION_REGIONS.items() if name.startswith(prefix))


def expression_label(name: str) -> str:
    """'mouthSmileLeft' -> 'Mouth: smile left'."""
    words = re.sub(r"([A-Z])", r" \1", name.lstrip("_")).lower().split()
    region = expression_region(name)
    if words and region.lower().startswith(words[0]):
        words = words[1:]
    return f"{region}: {' '.join(words) or name.lstrip('_')}"


# Every expression score the face model gives, kept as its own feature.
FEATURES.update({f"expr_{name}": expression_label(name) for name in EXPRESSIONS})
# Region of each feature, so results can be summed up by part of the face or body.
REGIONS = {
    "eyes_open": "Eyes", "eye_contact": "Eyes", "smile": "Mouth", "goofy": "Mouth",
    "head_straight": "Head angle", "chin_level": "Head angle", "left_side": "Head angle",
    "chin_up": "Head angle", "sharpness": "Photo quality", "face_in_frame": "Framing",
    "clean_crop": "Framing", "looking_room": "Framing", "body_turned": "Body angle",
    "facing_camera": "Body angle", "upright": "Posture", "long_neck": "Posture",
    "arms_away": "Posture", "hand_raised": "Posture",
    **{f"expr_{name}": expression_region(name) for name in EXPRESSIONS},
}
# Features with a direction rather than an amount: what a positive and a negative weight prefer.
SIDES = {
    "left_side": ("Your left side toward the camera", "Your right side toward the camera"),
    "chin_up": ("Chin up", "Chin down"),
}
# Head turn and chin angle are divided by this, so a quarter turn scores 1.
QUARTER_TURN = 90
# Head tilt or chin angle at or past this many degrees scores 0 on straightness.
MAX_ANGLE = 30
# Sharpness is log-scaled; this Laplacian variance and above scores 1.
SHARPEST = 1000
BODY_TURN = {"square": 0.0, "angled": 0.5, "side_on": 1.0}
VIEW_FACING = {"front": 1.0, "three_quarter": 2 / 3, "profile": 1 / 3, "back": 0.0}
# Space in front of a turned head, as a fraction of frame width, that counts as enough.
ENOUGH_LOOKING_ROOM = 0.3
# Weaker regularisation fits the choices more closely; a few dozen choices need it fairly strong.
REGULARISATION = 1.0
# Fraction of pairs picked at random instead of where the model is least sure, so every
# photo keeps getting shown.
EXPLORE = 0.3
# How many random pairs to score when looking for the least certain one.
CANDIDATE_PAIRS = 200
# When to stop asking: never before MIN_CHOICES, always at MAX_CHOICES, and in between once
# the top feature is CLEAR (see confidence) or the model guesses RIGHT_GUESSES of the last
# RECENT_GUESSES picks before they're made. In simulated pickers on our photos this stopped
# after a median of 23 picks with the strongest preference ranked first 88% of the time.
MIN_CHOICES = 15
MAX_CHOICES = 40
RECENT_GUESSES = 15
RIGHT_GUESSES = 12
# Confidence comes from refitting on this many resamples of the choices. Guess accuracy
# can't serve: the least certain pairs are shown on purpose, so even a perfectly
# consistent person's picks are hard to guess.
RESAMPLES = 100
# Share of resamples agreeing on the top feature from which it counts as clear or likely.
# Simulated random pickers reached CLEAR about 10% of the time and LIKELY about 20%.
CLEAR = 0.9
LIKELY = 0.7


def photo_features(result: dict) -> dict[str, Optional[float]]:
    """Features for one photo from vision.analyze(). None means it couldn't be measured.

    Only the largest face and the first body count: the app is about photos of one person.
    """
    faces = sorted(result["faces"], key=lambda f: f["bbox"]["h"], reverse=True)
    face = faces[0] if faces else None
    m = face.get("measurements", {}) if face else {}
    expressions = face.get("expressions", {}) if face else {}
    pose = face.get("pose") if face else None
    person = result["people"][0] if result["people"] else None
    # Posture fields are newer than the rest, so results without them still work.
    body = person or {}

    def straightness(angle: Optional[float]) -> Optional[float]:
        return None if angle is None else 1 - min(abs(angle), MAX_ANGLE) / MAX_ANGLE

    features = {
        "eyes_open": m.get("eye_openness"),
        "eye_contact": m.get("eyes_on_lens"),
        "smile": m.get("smile"),
        "goofy": None if face is None or "mode" not in face else float(face["mode"] == "goofy"),
        "head_straight": straightness(m.get("head_tilt")),
        "chin_level": straightness(m.get("chin_angle")),
        "sharpness": None if m.get("sharpness") is None
        else min(1.0, math.log1p(m["sharpness"]) / math.log1p(SHARPEST)),
        "face_in_frame": None if face is None else float(not face["cut_off"]),
        "clean_crop": None if person is None else float(person["cut_at_joint"] is None),
        "looking_room": None if person is None
        else float(person.get("looking_room", 1) >= ENOUGH_LOOKING_ROOM),
        "body_turned": None if person is None else BODY_TURN[person["body_turn"]],
        "facing_camera": None if person is None else VIEW_FACING[person["view"]],
        "upright": None if body.get("head_forward") is None else -body["head_forward"] / QUARTER_TURN,
        "long_neck": body.get("neck_length"),
        "arms_away": body.get("arm_gap"),
        "hand_raised": None if body.get("hand_raised") is None else float(body["hand_raised"]),
        # Negative yaw turns the head toward the image's left, which shows the camera
        # the person's left cheek; negative pitch is chin up. Checked on our own photos.
        "left_side": None if pose is None else -pose["yaw"] / QUARTER_TURN,
        "chin_up": None if pose is None else -pose["pitch"] / QUARTER_TURN,
    }
    features.update({f"expr_{name}": expressions.get(name) for name in EXPRESSIONS})
    return features


def preference(feature: str, label: str, weight: float) -> str:
    """What a weight says the person prefers, e.g. "Chin down" or "Smiling, less of it"."""
    if feature in SIDES:
        return SIDES[feature][0 if weight > 0 else 1]
    return f"{label}, {'more' if weight > 0 else 'less'} of it"


class Ranker:
    """Turns photo features and pairwise choices into feature weights and photo scores."""

    def __init__(self, features: dict[str, dict[str, Optional[float]]]):
        self.photos = list(features)
        self.index = {photo: i for i, photo in enumerate(self.photos)}
        raw = np.array([[np.nan if features[p][name] is None else features[p][name]
                         for name in FEATURES] for p in self.photos], dtype=float)
        # Standardise so weights compare across features. A missing value becomes the
        # average, so it neither helps nor hurts a photo.
        mean = np.nanmean(raw, axis=0) if len(raw) else np.zeros(len(FEATURES))
        std = np.nanstd(raw, axis=0) if len(raw) else np.ones(len(FEATURES))
        mean = np.nan_to_num(mean)
        # A feature that's the same in every photo can't explain any choice.
        self.varies = np.nan_to_num(std) > 0
        std = np.where(self.varies, std, 1.0)
        # Kept so saved weights can score new photos on the same scale.
        self.mean, self.std = mean, std
        self.x = np.nan_to_num((raw - mean) / std)
        self.weights = np.zeros(len(FEATURES))

    def fit(self, choices: list[tuple[str, str]]) -> None:
        """Learn weights from (winner, loser) pairs. Pairs with unknown photos are ignored."""
        self.weights = self.learn(choices)

    def learn(self, choices: list[tuple[str, str]]) -> np.ndarray:
        """The weights (winner, loser) pairs give, without changing this ranker's own."""
        diffs = [self.x[self.index[w]] - self.x[self.index[l]]
                 for w, l in choices if w in self.index and l in self.index]
        if not diffs:
            return np.zeros(len(FEATURES))
        d = np.array(diffs)
        # Each choice is shown both ways round so the model sees both outcomes.
        model = LogisticRegression(C=REGULARISATION, fit_intercept=False)
        model.fit(np.vstack([d, -d]), np.r_[np.ones(len(d)), np.zeros(len(d))])
        return model.coef_[0]

    def confidence(self, choices: list[tuple[str, str]]) -> float:
        """Share of resampled choice sets that agree on the current top feature and its direction."""
        if not self.weights.any() or not choices:
            return 0.0
        top = int(np.argmax(np.abs(self.weights)))
        rng = np.random.default_rng(0)
        agree = 0
        for _ in range(RESAMPLES):
            weights = self.learn([choices[i] for i in rng.integers(0, len(choices), len(choices))])
            pick = int(np.argmax(np.abs(weights)))
            agree += pick == top and (weights[pick] > 0) == (self.weights[top] > 0)
        return agree / RESAMPLES

    def stop_reason(self, choices: list[dict]) -> Optional[str]:
        """Why to stop asking ("limit", "clear" or "predictable"), or None to keep going.

        `choices` are dicts with "winner", "loser" and "model_agreed" (whether the model,
        before the pick, gave the winner better odds; None before it had learned anything).
        Expects this ranker to be fitted on the same choices.
        """
        if len(choices) >= MAX_CHOICES:
            return "limit"
        if len(choices) < MIN_CHOICES:
            return None
        if self.confidence([(c["winner"], c["loser"]) for c in choices]) >= CLEAR:
            return "clear"
        guesses = [c["model_agreed"] for c in choices[-RECENT_GUESSES:] if c["model_agreed"] is not None]
        if len(guesses) == RECENT_GUESSES and sum(guesses) >= RIGHT_GUESSES:
            return "predictable"
        return None

    def win_probability(self, a: str, b: str) -> float:
        """Chance the model gives photo a of being picked over photo b."""
        margin = (self.x[self.index[a]] - self.x[self.index[b]]) @ self.weights
        return float(1 / (1 + np.exp(-margin)))

    def scores(self) -> dict[str, float]:
        """Each photo's score; only the order and gaps mean anything."""
        return dict(zip(self.photos, (self.x @ self.weights).tolist()))

    def priorities(self) -> list[dict]:
        """Features, most influential first, with each one's share of the total influence."""
        total = float(np.abs(self.weights).sum())
        rows = [{"feature": name, "label": label, "weight": float(w),
                 "share": abs(float(w)) / total if total else 0.0, "varies": bool(varies),
                 "prefers": preference(name, label, float(w)), "region": REGIONS[name]}
                for (name, label), w, varies in zip(FEATURES.items(), self.weights, self.varies)]
        return sorted(rows, key=lambda r: r["share"], reverse=True)

    def region_shares(self, weights: Optional[np.ndarray] = None) -> dict[str, float]:
        """Each region's share of how much the score varies between photos.

        A region's influence is the spread of its features' combined contribution across the
        photos, not the sum of its weights: the mouth has two dozen features and the nose two,
        and noise in many small weights mostly cancels out where real preferences add up.
        """
        weights = self.weights if weights is None else weights
        spread = {}
        for region in dict.fromkeys(REGIONS.values()):
            columns = [i for i, name in enumerate(FEATURES) if REGIONS[name] == region]
            spread[region] = float(np.std(self.x[:, columns] @ weights[columns])) if len(self.x) else 0.0
        total = sum(spread.values())
        return {region: value / total if total else 0.0 for region, value in spread.items()}

    def region_confidence(self, choices: list[tuple[str, str]]) -> float:
        """Share of resampled choice sets that agree on the most influential region."""
        if not self.weights.any() or not choices:
            return 0.0
        shares = self.region_shares()
        top = max(shares, key=shares.get)
        rng = np.random.default_rng(0)
        agree = 0
        for _ in range(RESAMPLES):
            resampled = self.region_shares(self.learn([choices[i] for i in rng.integers(0, len(choices), len(choices))]))
            agree += max(resampled, key=resampled.get) == top
        return agree / RESAMPLES

    def export(self) -> dict:
        """Everything needed to score a new photo with these weights, as plain JSON-ready data.

        score = sum(weight * (feature - mean) / std), using the photo_features() values;
        a missing feature counts as the mean.
        """
        return {
            "regions": self.region_shares(),
            "priorities": [{k: r[k] for k in ("feature", "region", "prefers", "share", "weight")}
                           for r in self.priorities() if r["varies"]],
            "weights": dict(zip(FEATURES, map(float, self.weights))),
            "mean": dict(zip(FEATURES, map(float, self.mean))),
            "std": dict(zip(FEATURES, map(float, self.std))),
        }

    def next_pair(self, seen: set[frozenset], rng: random.Random) -> Optional[tuple[str, str]]:
        """A pair not compared yet: usually the one the model is least sure about."""
        if len(self.photos) < 2:
            return None
        candidates = []
        for _ in range(CANDIDATE_PAIRS):
            a, b = rng.sample(self.photos, 2)
            if frozenset((a, b)) not in seen:
                candidates.append((a, b))
        if not candidates:
            return None
        if not self.weights.any() or rng.random() < EXPLORE:
            return candidates[0]
        return min(candidates, key=lambda pair: abs(self.win_probability(*pair) - 0.5))
