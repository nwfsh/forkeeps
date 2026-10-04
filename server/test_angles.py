"""Run from server/:  python -m pytest test_angles.py"""
import random

import angles
from ranker import ALL_FEATURES


def frame(i: int, yaw: float, pitch: float = 0.0, roll: float = 0.0, eyes: float = 0.9) -> dict:
    face = {"bbox": {"h": 0.3}, "cut_off": False, "pose": {"yaw": yaw, "pitch": pitch, "roll": roll},
            "measurements": {"eye_openness": eyes, "head_tilt": roll, "chin_angle": pitch, "sharpness": 50.0}}
    return {"id": str(i), "analysis": {"faces": [face], "people": []}}


def turning_head(seed: int = 0) -> list:
    """Frames held at three angles: turned left, straight on, turned right with chin up."""
    rng = random.Random(seed)
    frames = []
    for yaw, pitch in ((-30, 0), (0, 0), (30, -15)):
        for _ in range(6):
            frames.append(frame(len(frames), yaw + rng.uniform(-3, 3), pitch + rng.uniform(-3, 3)))
    return frames


def test_finds_each_held_angle_once():
    result = angles.cluster(turning_head())
    labels = sorted(c["label"] for c in result["clusters"])
    assert labels == ["Left side", "Right side, chin up", "Straight on"]
    assert all(c["size"] == 6 for c in result["clusters"])


def test_representatives_are_real_frames_with_open_eyes():
    frames = turning_head()
    frames[0]["analysis"]["faces"][0]["measurements"]["eye_openness"] = 0.1
    frames[0]["analysis"]["faces"][0]["pose"] = {"yaw": -30.0, "pitch": 0.0, "roll": 0.0}  # dead centre
    ids = {f["id"] for f in frames}
    result = angles.cluster(frames)
    assert all(c["frame"] in ids for c in result["clusters"])
    assert "0" not in [c["frame"] for c in result["clusters"]]


def test_holding_still_gives_one_group():
    frames = [frame(i, random.Random(i).uniform(-2, 2)) for i in range(10)]
    assert len(angles.cluster(frames)["clusters"]) == 1


def test_frames_without_one_face_are_skipped():
    frames = turning_head()
    frames.append({"id": "empty", "analysis": {"faces": [], "people": []}})
    assert angles.cluster(frames)["skipped"] == 1
    assert angles.cluster(turning_head()[:3])["clusters"] == []


def test_angle_features_keep_only_head_angle():
    f = angles.angle_features(frame(0, -45, -9, 6)["analysis"])
    assert set(f) == set(ALL_FEATURES)
    assert f["left_side"] == 0.5 and f["chin_up"] == 0.1
    assert all(f[name] is None for name in ALL_FEATURES if name not in angles.ANGLE_FEATURES)
    assert angles.angle_features({"faces": [], "people": []}) is None


def test_labels_name_the_tilt_direction():
    assert angles.label({"yaw": 0, "pitch": 0, "roll": 20}) == "Straight on, tilted to your right"
    assert angles.label({"yaw": -20, "pitch": -10, "roll": -20}) == "Left side, chin up, tilted to your left"
