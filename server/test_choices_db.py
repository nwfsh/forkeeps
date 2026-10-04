"""Run from server/:  python -m pytest test_choices_db.py"""
import json

import pytest

import choices_db


@pytest.fixture(autouse=True)
def scratch_db(tmp_path, monkeypatch):
    monkeypatch.setattr(choices_db, "DB_PATH", tmp_path / "choices.db")


def test_add_and_load_keep_order_and_shape():
    choices_db.add("salma", "a.jpg", "b.jpg", None)
    choices_db.add("salma", "c.jpg", "a.jpg", True)
    choices_db.add("salma", "b.jpg", "c.jpg", False)
    choices = choices_db.load("salma")
    assert [(c["winner"], c["loser"], c["model_agreed"]) for c in choices] == [
        ("a.jpg", "b.jpg", None), ("c.jpg", "a.jpg", True), ("b.jpg", "c.jpg", False)]
    assert all(c["at"] for c in choices)


def test_people_are_kept_apart():
    choices_db.add("salma", "a.jpg", "b.jpg", None)
    choices_db.add("me", "x.jpg", "y.jpg", None)
    assert [c["winner"] for c in choices_db.load("salma")] == ["a.jpg"]
    assert [c["winner"] for c in choices_db.load("me")] == ["x.jpg"]


def test_names_are_cleaned_like_the_old_file_names():
    choices_db.add("Sal ma!", "a.jpg", "b.jpg", None)
    assert len(choices_db.load("Salma")) == 1
    choices_db.add("", "a.jpg", "b.jpg", None, at="2026-01-01T00:00:00+00:00")
    assert len(choices_db.load("me")) == 1


def test_remove_last_undoes_the_newest_pick_only():
    choices_db.add("salma", "a.jpg", "b.jpg", None)
    choices_db.add("salma", "c.jpg", "d.jpg", True)
    assert choices_db.remove_last("salma")["winner"] == "c.jpg"
    assert [c["winner"] for c in choices_db.load("salma")] == ["a.jpg"]
    choices_db.remove_last("salma")
    assert choices_db.remove_last("salma") is None


def test_clear_only_touches_that_person():
    choices_db.add("salma", "a.jpg", "b.jpg", None)
    choices_db.add("me", "x.jpg", "y.jpg", None)
    assert choices_db.clear("salma") == 1
    assert choices_db.load("salma") == []
    assert len(choices_db.load("me")) == 1


def test_import_json_matches_the_files_and_is_safe_to_repeat(tmp_path):
    saved = [{"winner": "a.jpg", "loser": "b.jpg", "model_agreed": None, "at": "2026-10-04T00:15:06+00:00"},
             {"winner": "b.jpg", "loser": "c.jpg", "model_agreed": True, "at": "2026-10-04T00:15:13+00:00"}]
    (tmp_path / "salma.json").write_text(json.dumps(saved))
    assert choices_db.import_json(tmp_path) == {"salma": 2}
    assert choices_db.import_json(tmp_path) == {"salma": 0}
    assert choices_db.load("salma") == saved


def test_weights_keep_history_but_skip_repeats():
    assert choices_db.save_weights("salma", 10, 0.5, {"weights": {"smile": 1.0}})
    assert not choices_db.save_weights("salma", 10, 0.5, {"weights": {"smile": 1.0}})
    assert choices_db.save_weights("salma", 12, 0.6, {"weights": {"smile": 0.8}})
    history = choices_db.weights_history("salma")
    assert [(h["picks"], h["weights"]["smile"]) for h in history] == [(10, 1.0), (12, 0.8)]
    assert choices_db.weights_history("sarah") == []


def test_windows_paths_match_mac_paths():
    choices_db.add("sarah", "data\\training-recognition\\sarah\\a.jpg", "data/training-recognition/sarah/b.jpg", None)
    assert choices_db.load("sarah")[0]["winner"] == "data/training-recognition/sarah/a.jpg"


def test_test_choices_are_kept_apart_from_training_picks():
    choices_db.add_test_choice("salma", "a.jpg", "b.jpg")
    choices_db.add_test_choice("salma", "c.jpg", "a.jpg")
    assert [(c["winner"], c["loser"]) for c in choices_db.load_test_choices("salma")] == [
        ("a.jpg", "b.jpg"), ("c.jpg", "a.jpg")]
    assert choices_db.load("salma") == []  # never used for training
    assert choices_db.remove_last_test_choice("salma")["winner"] == "c.jpg"
    assert len(choices_db.load_test_choices("salma")) == 1
