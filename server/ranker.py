"""Learn which photo features someone prioritises from "pick the better photo" choices.

Each photo becomes a row of features (higher always means "more of" the named thing).
Every choice says the winner's features beat the loser's, so a logistic regression on
feature differences (a Bradley-Terry model) learns one weight per feature: how much
more of that feature makes a photo more likely to win.
"""
import math
import random
from typing import Optional

import numpy as np
from sklearn.linear_model import LogisticRegression

# Feature name -> what it means, worded for the "what you prioritise" ranking.
FEATURES = {
    "eyes_open": "Eyes open",
    "eye_contact": "Looking at the camera",
    "smile": "Smiling",
    "goofy": "Goofy face",
    "head_straight": "Head held straight",
    "chin_level": "Chin level",
    "face_size": "Face fills the frame",
    "sharpness": "Sharp focus",
    "face_in_frame": "Face not cut off",
    "clean_crop": "Frame not cutting at a joint",
    "looking_room": "Space in the direction you look",
    "body_shown": "More of the body in frame",
    "body_turned": "Body angled to the camera",
    "facing_camera": "Facing the camera",
}
# Head tilt or chin angle at or past this many degrees scores 0 on straightness.
MAX_ANGLE = 30
# Sharpness is log-scaled; this Laplacian variance and above scores 1.
SHARPEST = 1000
CROP_SHOWN = {"head_only": 0.0, "shoulders_up": 0.25, "waist_up": 0.5, "knees_up": 0.75, "full_body": 1.0}
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
    person = result["people"][0] if result["people"] else None

    def straightness(angle: Optional[float]) -> Optional[float]:
        return None if angle is None else 1 - min(abs(angle), MAX_ANGLE) / MAX_ANGLE

    features = {
        "eyes_open": m.get("eye_openness"),
        "eye_contact": m.get("eyes_on_lens"),
        "smile": m.get("smile"),
        "goofy": None if face is None or "mode" not in face else float(face["mode"] == "goofy"),
        "head_straight": straightness(m.get("head_tilt")),
        "chin_level": straightness(m.get("chin_angle")),
        "face_size": m.get("face_size"),
        "sharpness": None if m.get("sharpness") is None
        else min(1.0, math.log1p(m["sharpness"]) / math.log1p(SHARPEST)),
        "face_in_frame": None if face is None else float(not face["cut_off"]),
        "clean_crop": None if person is None else float(person["cut_at_joint"] is None),
        "looking_room": None if person is None
        else float(person.get("looking_room", 1) >= ENOUGH_LOOKING_ROOM),
        "body_shown": None if person is None else CROP_SHOWN[person["crop"]],
        "body_turned": None if person is None else BODY_TURN[person["body_turn"]],
        "facing_camera": None if person is None else VIEW_FACING[person["view"]],
    }
    return features


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
                 "share": abs(float(w)) / total if total else 0.0, "varies": bool(varies)}
                for (name, label), w, varies in zip(FEATURES.items(), self.weights, self.varies)]
        return sorted(rows, key=lambda r: r["share"], reverse=True)

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
