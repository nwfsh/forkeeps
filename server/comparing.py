"""The app's "which do you like more?" session, run the way the Streamlit compare tool runs it.

The app sends its snapshots and the picks made so far; this fits a Ranker on them and answers
with the next pair to show (usually the one the model is least sure about) and whether to stop,
using the same rules as compare.py: never before MIN_CHOICES picks, always at MAX_CHOICES, and in
between once the top feature is clear or the model has been guessing the picks right.
"""
import random
from typing import Optional

from ranker import CLEAR, MAX_CHOICES, MIN_CHOICES, RECENT_GUESSES, RIGHT_GUESSES, Ranker, photo_features


def guesses(features: dict, picks: list[dict]) -> list[Optional[bool]]:
    """For each pick, whether a model fitted on the picks before it gave the winner better odds;
    None for ties and before the model had learned anything (compare.py's model_agreed)."""
    agreed, choices, ties = [], [], []
    for pick in picks:
        if pick.get("tie"):
            agreed.append(None)
            ties.append((pick["a"], pick["b"]))
            continue
        ranker = Ranker(features)
        ranker.fit(choices, ties)
        agreed.append(ranker.win_probability(pick["winner"], pick["loser"]) > 0.5 if ranker.weights.any() else None)
        choices.append((pick["winner"], pick["loser"]))
    return agreed


def stop_reason(ranker: Ranker, choices: list, agreed: list[Optional[bool]], count: int) -> Optional[str]:
    """Ranker.stop_reason's rules, counting ties as picks."""
    if count >= MAX_CHOICES:
        return "limit"
    if count < MIN_CHOICES:
        return None
    if choices and ranker.confidence(choices) >= CLEAR:
        return "clear"
    recent = [a for a in agreed[-RECENT_GUESSES:] if a is not None]
    if len(recent) == RECENT_GUESSES and sum(recent) >= RIGHT_GUESSES:
        return "predictable"
    return None


def next_step(candidates: list[dict], picks: list[dict], skipped: list[list[str]], seed: int = 0) -> dict:
    """{"pair": [a, b] or None, "stop": a reason or None, "picks", "min", "max"}.

    candidates are {"id", "analysis"}; picks are {"winner", "loser"} or {"a", "b", "tie": true};
    skipped are pairs passed over with "Can't decide", which aren't asked again.
    """
    if len(candidates) < 2:
        return {"pair": None, "stop": None, "picks": len(picks), "min": MIN_CHOICES, "max": MAX_CHOICES}
    features = {str(c["id"]): photo_features(c["analysis"]) for c in candidates}
    choices = [(p["winner"], p["loser"]) for p in picks if not p.get("tie")]
    ties = [(p["a"], p["b"]) for p in picks if p.get("tie")]
    ranker = Ranker(features)
    ranker.fit(choices, ties)
    stop = stop_reason(ranker, choices, guesses(features, picks), len(picks))
    seen = {frozenset(c) for c in choices + ties} | {frozenset(s) for s in skipped}
    pair = ranker.next_pair(seen, random.Random(seed + len(picks) + len(skipped)))
    return {"pair": list(pair) if pair else None, "stop": stop, "picks": len(picks),
            "min": MIN_CHOICES, "max": MAX_CHOICES}
