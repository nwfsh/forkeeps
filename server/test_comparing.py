"""Run from server/:  python -m pytest test_comparing.py"""
import pytest
from fastapi.testclient import TestClient

import choices_db
import comparing
import main
import ranker as R
import retrain
from test_snapshots import recording


@pytest.fixture(autouse=True)
def scratch_db(tmp_path, monkeypatch):
    monkeypatch.setattr(choices_db, "DB_PATH", tmp_path / "choices.db")
    # Retraining writes the person's weights file; keep it out of the real preferences/weights/.
    monkeypatch.setattr(retrain, "WEIGHTS_FOLDER", tmp_path / "weights")


def smile(frame):
    return frame["analysis"]["faces"][0]["measurements"]["smile"]


def run_session(frames, taste, tie_within=0.0):
    """Pick until the session says stop, like someone using the app. Returns the picks made."""
    by_id = {f["id"]: f for f in frames}
    picks = []
    while True:
        step = comparing.next_step(frames, picks, [])
        if step["stop"] or not step["pair"]:
            return picks, step
        a, b = step["pair"]
        if abs(taste(by_id[a]) - taste(by_id[b])) <= tie_within:
            picks.append({"a": a, "b": b, "tie": True})
        else:
            picks.append({"winner": a, "loser": b} if taste(by_id[a]) > taste(by_id[b]) else {"winner": b, "loser": a})


def test_stops_between_the_minimum_and_maximum_like_compare_py():
    picks, step = run_session(recording(20), lambda f: -smile(f))
    assert R.MIN_CHOICES <= len(picks) <= R.MAX_CHOICES and step["stop"] in ("clear", "predictable", "limit")


def test_never_asks_the_same_pair_twice():
    picks, _ = run_session(recording(20), lambda f: -smile(f))
    pairs = [frozenset((p.get("winner", p.get("a")), p.get("loser", p.get("b")))) for p in picks]
    assert len(pairs) == len(set(pairs))


def test_ties_count_as_picks_and_are_never_asked_again():
    frames = recording(20)
    picks = [{"a": frames[0]["id"], "b": frames[1]["id"], "tie": True}]
    step = comparing.next_step(frames, picks, [[frames[2]["id"], frames[3]["id"]]])
    assert step["picks"] == 1 and set(step["pair"]) not in ({frames[0]["id"], frames[1]["id"]}, {frames[2]["id"], frames[3]["id"]})


def test_learns_the_taste_with_ties_in_it():
    frames = recording(20)
    picks, _ = run_session(frames, lambda f: -smile(f), tie_within=0.1)
    assert any(p.get("tie") for p in picks)
    features = {f["id"]: R.photo_features(f["analysis"]) for f in frames}
    ranker = R.Ranker(features)
    ranker.fit([(p["winner"], p["loser"]) for p in picks if not p.get("tie")],
               [(p["a"], p["b"]) for p in picks if p.get("tie")])
    assert ranker.priorities()[0]["feature"] == "smile" and ranker.priorities()[0]["weight"] < 0


def test_a_tie_pulls_two_photos_scores_together():
    photos = {"a": {n: 0.0 for n in R.FEATURES}, "b": {n: 0.0 for n in R.FEATURES}, "c": {n: 0.0 for n in R.FEATURES}}
    photos["a"]["smile"], photos["b"]["smile"], photos["c"]["smile"] = 1.0, 0.0, 0.5
    alone, with_tie = R.Ranker(photos), R.Ranker(photos)
    alone.fit([("a", "b")] * 3)
    with_tie.fit([("a", "b")] * 3, [("a", "b")] * 3)
    assert abs(with_tie.weights[list(R.FEATURES).index("smile")]) < abs(alone.weights[list(R.FEATURES).index("smile")])


def test_endpoints_save_ties_and_retrain_uses_them():
    client = TestClient(main.app)
    frames = recording(20)
    step = client.post("/pairs/next", json={"candidates": frames}).json()
    assert len(step["pair"]) == 2 and step["stop"] is None
    a, b, c = frames[0], frames[1], frames[2]
    client.post("/picks", json={"person": "t", "winner": {"id": a["id"], "analysis": a["analysis"]},
                                "loser": {"id": b["id"], "analysis": b["analysis"]}})
    client.post("/picks", json={"person": "t", "winner": {"id": b["id"], "analysis": b["analysis"]},
                                "loser": {"id": c["id"], "analysis": c["analysis"]}, "tie": True})
    assert len(choices_db.load_ties("t")) == 1 and len(choices_db.load("t")) == 1
    assert client.post("/model/t/retrain").json()["pairs"] == 1
    assert client.post("/pairs/next", json={"candidates": [{"nope": 1}, {"nope": 2}]}).status_code == 400


def test_fewer_than_two_snapshots_gives_no_pair():
    assert comparing.next_step([], [], [])["pair"] is None
    assert comparing.next_step(recording(1), [], [])["pair"] is None
