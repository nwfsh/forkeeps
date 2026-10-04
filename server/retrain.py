"""Retrain someone's taste model from the app: the photos they kept and removed in review, and
the snapshots they compared two at a time in onboarding.

The app offers this once RETRAIN_AFTER photos have been reviewed since the last training.
The result is saved like compare.py's: a new row in the database's weight history, and
preferences/weights/<person>.json, which score.py and ranking.py read.

Run from server/:  python retrain.py me      (retrain now, whatever the count)
"""
import json
import random
import sys
from datetime import datetime, timezone

import choices_db
from ranker import Ranker, photo_features
from score import WEIGHTS_FOLDER, win_chance

# Reviewed photos since the last training before retraining is offered.
RETRAIN_AFTER = 10
# Every kept photo beats every removed one, which grows fast (40 kept x 40 removed is 1600
# pairs); a sample this size teaches the same and keeps the confidence check quick.
MAX_PAIRS = 400
# How many photos the app's "Tune" swiping asks about: the ones the current model is least
# sure of, where a like or dislike teaches it the most.
TUNE_PHOTOS = 10
# How many of the model's priorities a retrain reports from before and after.
SHOWN_PRIORITIES = 3


def saved_model(name: str):
    """The model the app currently scores with (preferences/weights/<person>.json), or None."""
    path = WEIGHTS_FOLDER / f"{choices_db.person_key(name)}.json"
    return json.loads(path.read_text()) if path.exists() else None


def uncertain(name: str, photos: list[dict], count: int = TUNE_PHOTOS) -> list[dict]:
    """The photos ({"id", "analysis"}) the current model is least sure about, most unsure first,
    each with its score: the model's chance it beats an average photo, where 0.5 is a coin flip.

    Photos whose measurements can't be trusted (no face, several people...) are left out, since a
    swipe on them would teach the model something false.
    """
    model = saved_model(name)
    if model is None:
        raise ValueError("No taste model yet: finish onboarding or review some photos first")
    scored = []
    for photo in photos:
        analysis = photo.get("analysis")
        if not analysis or analysis.get("red_flags"):
            continue
        try:
            scored.append({"id": photo["id"], "score": round(win_chance(photo_features(analysis), model), 3)})
        except (KeyError, TypeError):
            continue
    return sorted(scored, key=lambda p: abs(p["score"] - 0.5))[:count]


def summary_of(model: dict) -> dict:
    """The parts of a saved model worth showing: how sure it is and what it cares about most."""
    return {"confidence": model.get("confidence"), "priorities": model["priorities"][:SHOWN_PRIORITIES]}


def last_training(name: str):
    """The latest model trained from review verdicts, or None."""
    trained = [h for h in choices_db.weights_history(name) if "verdicts" in h]
    return trained[-1] if trained else None


def status(name: str) -> dict:
    """How many photos have been reviewed, how many since the last training, and whether
    retraining is worth offering."""
    verdicts = [v for v in choices_db.load_verdicts(name) if v["features"] is not None]
    kept = sum(v["verdict"] == "keep" for v in verdicts)
    last = last_training(name)
    new = len(verdicts) - (last["verdicts"] if last else 0)
    return {
        "reviewed": len(verdicts),
        "kept": kept,
        "removed": len(verdicts) - kept,
        "new_since_training": max(0, new),
        "retrain_after": RETRAIN_AFTER,
        # Learning needs something liked and something not, as well as enough new photos.
        "ready": new >= RETRAIN_AFTER and 0 < kept < len(verdicts),
        "last_trained": last["saved_at"] if last else None,
    }


def retrain(name: str) -> dict:
    """Learn from every reviewed photo and every comparison pick, and save the result. Returns
    the new model's summary."""
    features, pairs = choices_db.verdict_pairs(name)
    if len(pairs) > MAX_PAIRS:
        pairs = random.Random(0).sample(pairs, MAX_PAIRS)
    # Comparison picks are few and each one is a direct choice, so they're all kept.
    pick_features, picks, ties = choices_db.pick_pairs(name)
    features, pairs = {**features, **pick_features}, pairs + picks
    if not pairs:
        raise ValueError("Pick between some photos, or keep one and remove one, before retraining")
    # Kept to show what this retrain changed.
    before = saved_model(name)

    ranker = Ranker(features)
    ranker.fit(pairs, ties)
    confidence = round(ranker.region_confidence(pairs), 2)
    export = ranker.export()
    reviewed = len(features)
    # "verdicts" marks a model trained from review, and how many photos it saw.
    choices_db.save_weights(name, len(pairs), confidence, {**export, "verdicts": reviewed})

    WEIGHTS_FOLDER.mkdir(parents=True, exist_ok=True)
    (WEIGHTS_FOLDER / f"{choices_db.person_key(name)}.json").write_text(json.dumps({
        "person": name,
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "picks": len(pairs),
        "confidence": confidence,
        "source": "review",
        **export,
    }, indent=1))
    return {
        "reviewed": reviewed,
        "pairs": len(pairs),
        "confidence": confidence,
        "priorities": export["priorities"],
        "regions": export["regions"],
        # The model this one replaced, or None if it's the first.
        "before": summary_of(before) if before else None,
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    summary = retrain(sys.argv[1])
    print(f"Trained on {summary['reviewed']} reviewed photos ({summary['pairs']} pairs), "
          f"confidence {summary['confidence']:.0%}")
    for p in summary["priorities"]:
        print(f"  {p['prefers']} ({p['share']:.0%})")
