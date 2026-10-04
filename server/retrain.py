"""Retrain someone's taste model from the photos they kept and removed in the app's review.

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
from ranker import Ranker
from score import WEIGHTS_FOLDER

# Reviewed photos since the last training before retraining is offered.
RETRAIN_AFTER = 10
# Every kept photo beats every removed one, which grows fast (40 kept x 40 removed is 1600
# pairs); a sample this size teaches the same and keeps the confidence check quick.
MAX_PAIRS = 400


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
    """Learn from every reviewed photo and save the result. Returns the new model's summary."""
    features, pairs = choices_db.verdict_pairs(name)
    if not pairs:
        raise ValueError("Keep at least one photo and remove at least one before retraining")
    if len(pairs) > MAX_PAIRS:
        pairs = random.Random(0).sample(pairs, MAX_PAIRS)

    ranker = Ranker(features)
    ranker.fit(pairs)
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
        "priorities": export["priorities"][:5],
        "regions": export["regions"],
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    summary = retrain(sys.argv[1])
    print(f"Trained on {summary['reviewed']} reviewed photos ({summary['pairs']} pairs), "
          f"confidence {summary['confidence']:.0%}")
    for p in summary["priorities"]:
        print(f"  {p['prefers']} ({p['share']:.0%})")
