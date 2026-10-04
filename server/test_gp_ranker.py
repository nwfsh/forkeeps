"""Run from server/:  python -m pytest test_gp_ranker.py"""
import random

from gp_ranker import GPRanker
from ranker import FEATURES, Ranker

NAMES = list(FEATURES)


def photos(n=60, seed=0):
    rng = random.Random(seed)
    return {f"p{i}": {name: rng.uniform(-1, 1) for name in NAMES} for i in range(n)}


def picks_by(taste, feats, n=150, seed=1):
    rng = random.Random(seed)
    ids = list(feats)
    out = []
    for _ in range(n):
        a, b = rng.sample(ids, 2)
        out.append((a, b) if taste(feats[a]) > taste(feats[b]) else (b, a))
    return out


def agreement(model, feats, pairs):
    return sum(model.score_new(feats[w]) > model.score_new(feats[l]) for w, l in pairs) / len(pairs)


def test_learns_a_simple_preference_like_bradley_terry():
    feats = photos()
    taste = lambda f: -f["chin_up"]
    gp = GPRanker(feats)
    gp.fit(picks_by(taste, feats))
    assert agreement(gp, feats, picks_by(taste, feats, seed=2)) > 0.85


def test_learns_features_combining_which_bradley_terry_cant():
    # Chin down only helps with a soft smile: the two features combine.
    feats = photos(80)
    taste = lambda f: -f["chin_up"] * (1 if f["smile"] < 0 else -1)
    train, test = picks_by(taste, feats, 200), picks_by(taste, feats, 200, seed=3)
    gp, bt = GPRanker(feats), Ranker(feats)
    gp.fit(train)
    bt.fit(train)
    assert agreement(gp, feats, test) > agreement(bt, feats, test) + 0.1


def test_ties_and_unknown_photos_are_handled():
    feats = photos(10)
    gp = GPRanker(feats)
    gp.fit([("p0", "p1"), ("p2", "nowhere")], ties=[("p3", "p4")])
    assert gp.score_new(feats["p0"]) > gp.score_new(feats["p1"])
    empty = GPRanker(feats)
    empty.fit([])
    assert empty.score_new(feats["p0"]) == 0.0 and empty.win_probability_new(feats["p0"], feats["p1"]) == 0.5
