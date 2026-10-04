"""Run from server/:  python -m pytest test_verdicts.py"""
import pytest
from fastapi.testclient import TestClient

import choices_db
import main
from ranker import Ranker

ANALYSIS = {
    "faces": [{"bbox": {"x": 0.3, "y": 0.2, "w": 0.3, "h": 0.3}, "cut_off": False, "mode": "smiling",
               "measurements": {"eye_openness": 0.9, "eyes_on_lens": 0.8, "smile": 0.7, "head_tilt": 2.0,
                                "chin_angle": 1.0, "face_size": 0.3, "sharpness": 400.0},
               "lighting": {"brightness": 0.7, "contour": 0.05}}],
    "people": [],
}


@pytest.fixture(autouse=True)
def scratch_db(tmp_path, monkeypatch):
    monkeypatch.setattr(choices_db, "DB_PATH", tmp_path / "choices.db")


def test_saves_features_not_the_analysis():
    choices_db.save_verdict("me", "1001", "keep", {"smile": 0.7})
    [verdict] = choices_db.load_verdicts("me")
    assert verdict["verdict"] == "keep" and verdict["features"] == {"smile": 0.7}


def test_reviewing_again_replaces_the_verdict_but_keeps_features():
    choices_db.save_verdict("me", "1001", "keep", {"smile": 0.7})
    choices_db.save_verdict("me", "1001", "remove", None)
    [verdict] = choices_db.load_verdicts("me")
    assert verdict["verdict"] == "remove" and verdict["features"] == {"smile": 0.7}


def test_rejects_unknown_verdicts():
    with pytest.raises(ValueError):
        choices_db.save_verdict("me", "1001", "maybe", None)


def test_every_kept_photo_beats_every_removed_one():
    for photo, verdict in (("1", "keep"), ("2", "keep"), ("3", "remove"), ("4", "remove")):
        choices_db.save_verdict("me", photo, verdict, {"smile": 0.5})
    choices_db.save_verdict("me", "5", "remove", None)  # unmeasured photos can't train anything
    features, pairs = choices_db.verdict_pairs("me")
    assert set(features) == {"app/1", "app/2", "app/3", "app/4"}
    assert sorted(pairs) == [("app/1", "app/3"), ("app/1", "app/4"), ("app/2", "app/3"), ("app/2", "app/4")]


def test_a_ranker_learns_from_verdicts():
    from test_ranker import made_up_photos
    photos = made_up_photos(20)
    smiliest = sorted(photos, key=lambda p: photos[p]["smile"])
    for photo in smiliest[:8]:
        choices_db.save_verdict("me", photo, "remove", photos[photo])
    for photo in smiliest[-8:]:
        choices_db.save_verdict("me", photo, "keep", photos[photo])
    features, pairs = choices_db.verdict_pairs("me")
    ranker = Ranker(features)
    ranker.fit(pairs)
    assert ranker.priorities()[0]["feature"] == "smile"


def test_endpoint_turns_analysis_into_features():
    client = TestClient(main.app)
    res = client.post("/verdicts", json={"person": "me", "photo": "1001", "verdict": "keep", "analysis": ANALYSIS})
    assert res.json() == {"saved": True, "measured": True}
    [verdict] = choices_db.load_verdicts("me")
    assert verdict["features"]["smile"] == 0.7
    assert verdict["features"]["bright_face"] == 0.7
    assert "landmarks" not in str(verdict["features"])


def test_endpoint_accepts_photos_without_analysis_and_rejects_bad_input():
    client = TestClient(main.app)
    assert client.post("/verdicts", json={"person": "me", "photo": "1", "verdict": "remove"}).json() == \
        {"saved": True, "measured": False}
    assert client.post("/verdicts", json={"person": "me", "photo": "1", "verdict": "maybe"}).status_code == 400
    assert client.post("/verdicts", json={"person": "me", "photo": "1", "verdict": "keep",
                                          "analysis": {"nonsense": 1}}).status_code == 400


def test_angle_verdicts_keep_only_head_angle():
    client = TestClient(main.app)
    analysis = {**ANALYSIS, "faces": [{**ANALYSIS["faces"][0], "pose": {"yaw": -45.0, "pitch": 0.0, "roll": 0.0}}]}
    res = client.post("/verdicts", json={"person": "me", "photo": "angle-1-3", "verdict": "keep",
                                         "analysis": analysis, "kind": "angle"})
    assert res.json() == {"saved": True, "measured": True}
    [verdict] = choices_db.load_verdicts("me")
    assert verdict["features"]["left_side"] == 0.5
    assert verdict["features"]["smile"] is None and verdict["features"]["bright_face"] is None


def test_cluster_endpoint():
    from test_angles import turning_head
    client = TestClient(main.app)
    res = client.post("/angles/cluster", json={"frames": turning_head()}).json()
    assert len(res["clusters"]) == 3 and res["skipped"] == 0
    assert client.post("/angles/cluster", json={"frames": [{"nope": 1}]}).status_code == 400
