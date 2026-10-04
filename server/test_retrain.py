"""Run from server/:  python -m pytest test_retrain.py"""
import json

import pytest
from fastapi.testclient import TestClient

import choices_db
import main
import retrain
from test_ranker import made_up_photos


@pytest.fixture(autouse=True)
def scratch(tmp_path, monkeypatch):
    monkeypatch.setattr(choices_db, "DB_PATH", tmp_path / "choices.db")
    monkeypatch.setattr(retrain, "WEIGHTS_FOLDER", tmp_path / "weights")


def review(count: int, seed: int = 0) -> None:
    """Keep the smilier half of some made-up photos and remove the rest."""
    photos = made_up_photos(count, seed)
    median = sorted(p["smile"] for p in photos.values())[count // 2]
    for name, features in photos.items():
        choices_db.save_verdict("me", f"{seed}-{name}", "keep" if features["smile"] >= median else "remove", features)


def test_not_ready_until_enough_new_photos():
    review(retrain.RETRAIN_AFTER - 1)
    assert not retrain.status("me")["ready"]
    review(1, seed=1)
    status = retrain.status("me")
    assert status["ready"] and status["new_since_training"] == retrain.RETRAIN_AFTER


def test_not_ready_if_everything_was_kept():
    for i in range(retrain.RETRAIN_AFTER):
        choices_db.save_verdict("me", str(i), "keep", {"smile": 0.5})
    assert not retrain.status("me")["ready"]
    with pytest.raises(ValueError):
        retrain.retrain("me")


def test_retraining_learns_the_taste_and_resets_the_count(tmp_path):
    review(30)
    summary = retrain.retrain("me")
    assert summary["priorities"][0]["feature"] == "smile"
    assert summary["reviewed"] == 30
    status = retrain.status("me")
    assert status["new_since_training"] == 0 and not status["ready"] and status["last_trained"]
    saved = json.loads((tmp_path / "weights" / "me.json").read_text())
    assert saved["source"] == "review" and saved["weights"]["smile"] > 0


def test_count_restarts_from_the_last_training():
    review(12)
    retrain.retrain("me")
    review(4, seed=1)
    assert retrain.status("me")["new_since_training"] == 4


def test_large_reviews_are_sampled():
    review(60)
    assert retrain.retrain("me")["pairs"] == retrain.MAX_PAIRS


def test_endpoints():
    client = TestClient(main.app)
    assert client.get("/model/me").json()["ready"] is False
    assert client.post("/model/me/retrain").status_code == 400
    review(retrain.RETRAIN_AFTER)
    assert client.get("/model/me").json()["ready"] is True
    res = client.post("/model/me/retrain").json()
    assert res["reviewed"] == retrain.RETRAIN_AFTER and res["status"]["ready"] is False
