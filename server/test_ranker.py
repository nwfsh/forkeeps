"""Run from server/:  python -m pytest test_ranker.py"""
import random

import pytest

import ranker as R
from ranker import FEATURES, Ranker, photo_features


def made_up_photos(count: int, seed: int = 0) -> dict:
    """Photos with every feature drawn at random between 0 and 1."""
    rng = random.Random(seed)
    return {f"photo{i}.jpg": {name: rng.random() for name in FEATURES} for i in range(count)}


def simulate(photos: dict, taste, rounds: int, seed: int = 0) -> Ranker:
    """Let a pretend person with preference function `taste` pick from the ranker's pairs."""
    ranker = Ranker(photos)
    rng = random.Random(seed)
    choices, seen = [], set()
    for _ in range(rounds):
        a, b = ranker.next_pair(seen, rng)
        seen.add(frozenset((a, b)))
        choices.append((a, b) if taste(photos[a]) >= taste(photos[b]) else (b, a))
        ranker.fit(choices)
    return ranker


def run_until_stop(photos: dict, taste, seed: int = 0):
    """A pretend person picks until the ranker says to stop. `taste` None picks at random.

    Returns the ranker, the choices as the app saves them, and the stop reason.
    """
    ranker = Ranker(photos)
    rng = random.Random(seed)
    choices, seen = [], set()
    while not (reason := ranker.stop_reason(choices)):
        a, b = ranker.next_pair(seen, rng)
        seen.add(frozenset((a, b)))
        if taste is None:
            winner, loser = (a, b) if rng.random() < 0.5 else (b, a)
        else:
            winner, loser = (a, b) if taste(photos[a]) >= taste(photos[b]) else (b, a)
        agreed = ranker.win_probability(winner, loser) > 0.5 if ranker.weights.any() else None
        choices.append({"winner": winner, "loser": loser, "model_agreed": agreed})
        ranker.fit([(c["winner"], c["loser"]) for c in choices])
    return ranker, choices, reason


def test_learns_single_priority():
    ranker = simulate(made_up_photos(40), lambda f: f["smile"], rounds=30)
    top = ranker.priorities()[0]
    assert top["feature"] == "smile"
    assert top["weight"] > 0


def test_learns_a_feature_they_dislike():
    ranker = simulate(made_up_photos(40), lambda f: -f["eye_contact"], rounds=30)
    top = ranker.priorities()[0]
    assert top["feature"] == "eye_contact"
    assert top["weight"] < 0


def test_ranks_two_priorities_above_the_rest():
    ranker = simulate(made_up_photos(60), lambda f: 2 * f["eye_contact"] + f["chin_up"], rounds=60)
    order = [row["feature"] for row in ranker.priorities()]
    assert order[:2] == ["eye_contact", "chin_up"]


def test_scores_order_photos_by_taste():
    photos = made_up_photos(40)
    ranker = simulate(photos, lambda f: f["smile"], rounds=30)
    scores = ranker.scores()
    best, worst = max(scores, key=scores.get), min(scores, key=scores.get)
    assert photos[best]["smile"] > photos[worst]["smile"]


def test_missing_values_neither_help_nor_hurt():
    photos = made_up_photos(10)
    photos["no_face.jpg"] = {name: None for name in FEATURES}
    ranker = Ranker(photos)
    ranker.fit([("photo0.jpg", "photo1.jpg")])
    assert ranker.scores()["no_face.jpg"] == pytest.approx(0)


def test_no_choices_means_no_priorities():
    ranker = Ranker(made_up_photos(5))
    ranker.fit([])
    assert all(row["share"] == 0 for row in ranker.priorities())


def test_feature_same_in_every_photo_is_flagged():
    photos = made_up_photos(10)
    for features in photos.values():
        features["left_side"] = 1.0
    rows = {row["feature"]: row for row in Ranker(photos).priorities()}
    assert not rows["left_side"]["varies"]
    assert rows["smile"]["varies"]


def test_next_pair_never_repeats():
    ranker = Ranker(made_up_photos(4))
    rng, seen = random.Random(0), set()
    for _ in range(6):  # 4 photos make exactly 6 pairs
        pair = ranker.next_pair(seen, rng)
        assert frozenset(pair) not in seen
        seen.add(frozenset(pair))
    assert ranker.next_pair(seen, rng) is None


def test_photo_features_from_analysis():
    result = {
        "faces": [{"bbox": {"h": 0.3}, "cut_off": False, "mode": "smiling",
                   "measurements": {"eye_openness": 0.9, "eyes_on_lens": 0.8, "smile": 0.7,
                                    "head_tilt": -15.0, "chin_angle": 0.0, "face_size": 0.3,
                                    "sharpness": 1000.0}}],
        "people": [{"view": "three_quarter", "body_turn": "angled", "crop": "waist_up",
                    "cut_at_joint": "hips", "looking_room": 0.1}],
    }
    f = photo_features(result)
    assert f["head_straight"] == pytest.approx(0.5)
    assert f["chin_level"] == 1
    assert f["sharpness"] == pytest.approx(1)
    assert f["goofy"] == 0
    assert f["clean_crop"] == 0
    assert f["looking_room"] == 0
    assert "face_size" not in f and "body_shown" not in f


def test_photo_features_without_anyone():
    f = photo_features({"faces": [], "people": []})
    assert all(value is None for value in f.values())


def test_keeps_asking_before_the_minimum():
    choices = [{"winner": "photo0.jpg", "loser": "photo1.jpg", "model_agreed": True}] * (R.MIN_CHOICES - 1)
    assert Ranker(made_up_photos(5)).stop_reason(choices) is None


def test_always_stops_at_the_maximum():
    choices = [{"winner": "photo0.jpg", "loser": "photo1.jpg", "model_agreed": False}] * R.MAX_CHOICES
    assert Ranker(made_up_photos(5)).stop_reason(choices) == "limit"


def test_stops_when_the_model_guesses_picks():
    # Pairs of identical photos teach the model nothing, so only the guesses can stop it.
    photos = {name: dict.fromkeys(FEATURES, 0.5) for name in ("a.jpg", "b.jpg")}
    choices = [{"winner": "a.jpg", "loser": "b.jpg", "model_agreed": True}] * R.MIN_CHOICES
    assert Ranker(photos).stop_reason(choices) == "predictable"


def test_consistent_people_stop_early_with_the_right_answer():
    stopped_right = 0
    for seed in range(10):
        ranker, _, reason = run_until_stop(made_up_photos(40, seed), lambda f: f["smile"], seed)
        top = ranker.priorities()[0]
        stopped_right += reason != "limit" and top["feature"] == "smile" and top["weight"] > 0
    assert stopped_right >= 9


def test_random_picks_rarely_look_clear():
    looked_clear = 0
    for seed in range(10):
        ranker, choices, _ = run_until_stop(made_up_photos(40, seed), None, seed)
        looked_clear += ranker.confidence([(c["winner"], c["loser"]) for c in choices]) >= R.CLEAR
    assert looked_clear <= 2
