"""Pick the snapshots someone swipes on in onboarding, from frames of a short recording.

A recording catches a hundred or so frames, mostly near-copies of each other. Swiping on
near-copies teaches the ranker little, so this keeps frames it can measure, groups them by the
features the ranker learns from, and picks one clear frame from each group: about twenty
snapshots that differ in look, smile, teeth, chin and face turn.
"""
import numpy as np
from sklearn.cluster import KMeans

from ranker import ACTIVE_FEATURES, photo_features

SNAPSHOTS = 20
# Fewer usable frames than this can't give a set worth swiping on.
MIN_FRAMES = 8
# A frame's eyes must be at least this open to represent its group, if any other's are.
EYES_OPEN = 0.6
# The features the snapshots should spread across: the active ones that aren't a squared copy.
SPREAD = tuple(name for name in ACTIVE_FEATURES if not name.endswith("_curve"))


def usable(result: dict) -> bool:
    """One measured face and nothing that makes its measurements untrustworthy."""
    faces = result.get("faces", [])
    return (len(faces) == 1 and "measurements" in faces[0] and not result.get("red_flags"))


def point(features: dict) -> np.ndarray:
    """A frame's position in SPREAD; NaN where a feature couldn't be measured (teeth aren't
    measured with the head turned well away, for instance)."""
    return np.array([np.nan if features.get(name) is None else features[name] for name in SPREAD], dtype=float)


def pick(frames: list[dict], count: int = SNAPSHOTS) -> dict:
    """{"snapshots": frame ids, most typical groups first, "usable": how many frames qualified}.

    Each frame is {"id", "analysis"}, the analysis being a /analyze result.
    """
    ids, points, eyes = [], [], []
    for frame in frames:
        result = frame["analysis"]
        if not usable(result):
            continue
        features = photo_features(result)
        ids.append(str(frame["id"]))
        points.append(point(features))
        eyes.append(features.get("eyes_open") or 0.0)
    if len(ids) < MIN_FRAMES:
        return {"snapshots": [], "usable": len(ids)}

    x = np.array(points)
    # A feature a frame couldn't measure counts as average, like it does for the ranker.
    centre = np.nan_to_num(np.nanmean(x, axis=0))
    x = np.where(np.isnan(x), centre, x)
    # Every feature on the same scale, so a turn of the head doesn't outweigh a smile.
    spread = x.std(axis=0)
    x = (x - centre) / np.where(spread > 0, spread, 1.0)
    k = min(count, len(ids))
    model = KMeans(n_clusters=k, n_init=10, random_state=0).fit(x)

    chosen = []
    for group in np.argsort(-np.bincount(model.labels_, minlength=k)):
        members = np.flatnonzero(model.labels_ == group)
        if members.size == 0:
            continue
        # The frame nearest the group's centre, among those with eyes open if there are any.
        open_eyes = [m for m in members if eyes[m] >= EYES_OPEN]
        candidates = np.array(open_eyes or members)
        nearest = candidates[np.argmin(np.linalg.norm(x[candidates] - model.cluster_centers_[group], axis=1))]
        chosen.append(ids[nearest])
    return {"snapshots": chosen, "usable": len(ids)}
