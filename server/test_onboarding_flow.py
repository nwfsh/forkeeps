"""The app's onboarding, end to end through the server, as the app calls it.

Run from server/:  python -m pytest test_onboarding_flow.py
"""
import pytest
from fastapi.testclient import TestClient

import choices_db
import main
import retrain
import shots
from test_snapshots import recording


@pytest.fixture(autouse=True)
def scratch(tmp_path, monkeypatch):
    """A scratch database and weights folder, so real profiles aren't touched."""
    monkeypatch.setattr(choices_db, "DB_PATH", tmp_path / "choices.db")
    monkeypatch.setattr(retrain, "WEIGHTS_FOLDER", tmp_path / "weights")
    monkeypatch.setattr(shots, "WEIGHTS_FOLDER", tmp_path / "weights")


def test_record_compare_train_then_coach():
    client = TestClient(main.app)
    frames = {f["id"]: f for f in recording()}

    # Record: the app sends the recording's frames and gets snapshots to swipe on.
    picked = client.post("/snapshots", json={"frames": list(frames.values())}).json()["snapshots"]
    assert len(picked) == 20

    # Compare: this person always picks the snapshot with less smile.
    for a, b in zip(picked, picked[1:] + picked[:1]):
        smile = {p: frames[p]["analysis"]["faces"][0]["measurements"]["smile"] for p in (a, b)}
        winner, loser = (a, b) if smile[a] < smile[b] else (b, a)
        res = client.post("/picks", json={"person": "newbie",
                                          "winner": {"id": f"onboarding-1-{winner}", "analysis": frames[winner]["analysis"]},
                                          "loser": {"id": f"onboarding-1-{loser}", "analysis": frames[loser]["analysis"]}})
        assert res.json() == {"saved": True}

    # Your profile: retraining learns that they'd rather not smile.
    summary = client.post("/model/newbie/retrain").json()
    assert summary["priorities"][0]["feature"] == "smile" and summary["priorities"][0]["weight"] < 0

    # Camera: a smiling frame, scored with the new profile, gets told to relax the smile.
    smiling = next(f for f in frames.values() if f["analysis"]["faces"][0]["measurements"]["smile"] > 0.8)
    shot = shots.judge({**smiling["analysis"], "warnings": []}, shots.load_model("newbie"))
    assert shot["scored_by"] == "model" and shot["instruction"]["clip"] == "relax_smile"


def test_retraining_combines_picks_and_review_swipes():
    client = TestClient(main.app)
    frames = recording(40)
    for a, b in zip(frames[:10], frames[10:20]):
        client.post("/picks", json={"person": "both", "winner": {"id": a["id"], "analysis": a["analysis"]},
                                    "loser": {"id": b["id"], "analysis": b["analysis"]}})
    for f, verdict in zip(frames[20:24], ("keep", "keep", "remove", "remove")):
        client.post("/verdicts", json={"person": "both", "photo": f["id"], "verdict": verdict, "analysis": f["analysis"]})
    summary = client.post("/model/both/retrain").json()
    assert summary["pairs"] == 10 + 2 * 2


def test_pick_rejects_bad_analysis():
    client = TestClient(main.app)
    bad = {"person": "x", "winner": {"id": "1", "analysis": {"nope": 1}}, "loser": {"id": "2", "analysis": {"nope": 1}}}
    assert client.post("/picks", json=bad).status_code == 400
