"""Run from server/:  python -m pytest test_snapshots.py"""
import random

from fastapi.testclient import TestClient

import main
import snapshots


def frame(i: int, smile: float, yaw: float, pitch: float = 0.0, blink: float = 0.1, flags=()) -> dict:
    """A /analyze-shaped frame with one face."""
    return {"id": str(i), "analysis": {
        "faces": [{"bbox": {"x": 0.3, "y": 0.2, "w": 0.3, "h": 0.3}, "cut_off": False, "mode": "serious",
                   "pose": {"yaw": yaw, "pitch": pitch, "roll": 0.0},
                   "measurements": {"eye_openness": 1 - blink, "eyes_on_lens": 0.8, "smile": smile,
                                    "head_tilt": 0.0, "chin_angle": pitch, "face_size": 0.3, "sharpness": 300.0},
                   "shape": {"teeth_shown": smile / 2} if abs(yaw) <= 30 else {}}],
        "people": [], "red_flags": list(flags), "warnings": []}}


def recording(count: int = 120) -> list[dict]:
    """Someone smiling more or less while turning their head side to side."""
    rng = random.Random(0)
    return [frame(i, smile=rng.random(), yaw=rng.uniform(-40, 40), pitch=rng.uniform(-15, 15)) for i in range(count)]


def test_picks_about_twenty_distinct_frames():
    result = snapshots.pick(recording())
    assert len(result["snapshots"]) == snapshots.SNAPSHOTS == len(set(result["snapshots"]))
    assert result["usable"] == 120


def test_snapshots_spread_across_smile_and_turn():
    frames = {f["id"]: f for f in recording()}
    chosen = [frames[i]["analysis"]["faces"][0] for i in snapshots.pick(list(frames.values()))["snapshots"]]
    smiles = [f["measurements"]["smile"] for f in chosen]
    yaws = [f["pose"]["yaw"] for f in chosen]
    assert max(smiles) - min(smiles) > 0.6 and max(yaws) - min(yaws) > 50


def test_turned_frames_without_teeth_measured_still_count():
    frames = [frame(i, smile=0.5, yaw=-38 if i % 2 else 38) for i in range(20)]
    assert snapshots.pick(frames)["usable"] == 20


def test_unusable_frames_are_left_out():
    frames = recording(30) + [frame(100, 0.5, 0.0, flags=["face_cut_off"])]
    frames[0]["analysis"]["faces"] = []
    result = snapshots.pick(frames)
    assert result["usable"] == 29 and "100" not in result["snapshots"] and "0" not in result["snapshots"]


def test_too_few_frames_gives_no_snapshots():
    assert snapshots.pick(recording(5)) == {"snapshots": [], "usable": 5}


def test_prefers_open_eyes_within_a_group():
    frames = [frame(i, 0.5, 0.0, blink=0.9 if i else 0.1) for i in range(10)]
    assert snapshots.pick(frames, count=1)["snapshots"] == ["0"]


def test_endpoint():
    client = TestClient(main.app)
    res = client.post("/snapshots", json={"frames": recording(40), "count": 10}).json()
    assert len(res["snapshots"]) == 10
    assert client.post("/snapshots", json={"frames": [{"nope": 1}]}).status_code == 400
