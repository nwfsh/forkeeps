"""The angle finder: group frames of someone slowly turning their head by head angle, and
pick one typical frame from each group for them to choose favourites from.

Frames come from the app's live analysis, so they're small and can be blurry. They only teach
the ranker about head angle: angle_features() blanks every other feature, and a blank
feature counts as average, so it can't push any other preference either way.
"""
from typing import Optional

import numpy as np
from sklearn.cluster import KMeans

from ranker import ALL_FEATURES, photo_features

# The ranker features that describe head angle and nothing else.
ANGLE_FEATURES = ("left_side", "chin_up", "head_straight", "chin_level")
MAX_CLUSTERS = 5
# Fewer usable frames than this can't show enough different angles to choose between.
MIN_FRAMES = 6
# Groups closer than this many degrees on every axis look the same, so k is lowered until
# they aren't.
DISTINCT = 6.0
# Frames with eyes less open than this aren't picked to represent a group if any other is.
EYES_OPEN = 0.6
# How far (degrees) a turn or tilt must go before the label mentions it.
TURNED, TILTED, CHIN = 12, 8, 8


def angle_features(result: dict) -> Optional[dict]:
    """Ranker features with only head angle filled in, or None if the head wasn't measured."""
    features = photo_features(result)
    if all(features[name] is None for name in ANGLE_FEATURES):
        return None
    return {name: features[name] if name in ANGLE_FEATURES else None for name in ALL_FEATURES}


def pose(result: dict) -> Optional[dict]:
    """The head pose of the only face in the frame, or None."""
    faces = result.get("faces", [])
    return faces[0].get("pose") if len(faces) == 1 else None


def label(p: dict) -> str:
    """Plain words for a pose, e.g. "Left side, chin up". Negative yaw shows the camera the
    person's left cheek and negative pitch is chin up (see ranker.photo_features); positive roll
    tips the head toward their right shoulder (checked on our own photos)."""
    parts = []
    if p["yaw"] <= -TURNED:
        parts.append("Left side")
    elif p["yaw"] >= TURNED:
        parts.append("Right side")
    else:
        parts.append("Straight on")
    if p["pitch"] <= -CHIN:
        parts.append("chin up")
    elif p["pitch"] >= CHIN:
        parts.append("chin down")
    if p["roll"] >= TILTED:
        parts.append("tilted to your right")
    elif p["roll"] <= -TILTED:
        parts.append("tilted to your left")
    return ", ".join(parts)


def cluster(frames: list[dict]) -> dict:
    """Group frames ({"id", "analysis"}) by head pose; one representative frame per group.

    Returns {"clusters": [{"frame", "size", "pose", "label"}], "skipped"}, biggest group first.
    """
    usable = [(f["id"], pose(f["analysis"]), f["analysis"]) for f in frames]
    usable = [(i, p, a) for i, p, a in usable if p is not None]
    skipped = len(frames) - len(usable)
    if len(usable) < MIN_FRAMES:
        return {"clusters": [], "skipped": skipped}

    points = np.array([[p["yaw"], p["pitch"], p["roll"]] for _, p, _ in usable])
    for k in range(min(MAX_CLUSTERS, len(usable) // 2), 0, -1):
        model = KMeans(n_clusters=k, n_init=10, random_state=0).fit(points)
        centres = model.cluster_centers_
        gaps = [np.max(np.abs(a - b)) for i, a in enumerate(centres) for b in centres[i + 1:]]
        if k == 1 or min(gaps) >= DISTINCT:
            break

    clusters = []
    for c, centre in enumerate(centres):
        members = [i for i, group in enumerate(model.labels_) if group == c]
        eyes_open = [i for i in members if (usable[i][2]["faces"][0].get("measurements", {})
                                           .get("eye_openness", 1) >= EYES_OPEN)]
        candidates = eyes_open or members
        best = min(candidates, key=lambda i: np.linalg.norm(points[i] - centre))
        p = {k: round(float(v), 1) for k, v in zip(("yaw", "pitch", "roll"), centre)}
        clusters.append({"frame": usable[best][0], "size": len(members), "pose": p, "label": label(p)})
    clusters.sort(key=lambda c: c["size"], reverse=True)
    return {"clusters": clusters, "skipped": skipped}
