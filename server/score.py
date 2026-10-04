"""Score new photos with someone's saved weights, best first.

Run from server/:  python score.py avery ../data/training-recognition/avery/testing_data

The weights come from preferences/weights/<person>.json, which compare.py writes when it
shows that person's results. Each score is the chance the photo would beat an average
photo from the ones the weights were trained on.
"""
import json
import math
import sys
from pathlib import Path

import vision
from ranker import photo_features

WEIGHTS_FOLDER = Path(__file__).resolve().parent / "preferences" / "weights"
PHOTO_TYPES = {".jpg", ".jpeg", ".png", ".heic"}
# Chance of beating an average photo above or below which a photo is a likely pick or skip.
LIKELY_PICK = 0.6
LIKELY_SKIP = 0.4


def win_chance(features: dict, saved: dict) -> float:
    """The saved weights' chance this photo beats an average training photo."""
    score = sum(weight * ((features[name] if features.get(name) is not None else saved["mean"][name])
                          - saved["mean"][name]) / saved["std"][name]
                for name, weight in saved["weights"].items())
    return 1 / (1 + math.exp(-score))


def main(person: str, folder: str) -> None:
    saved = json.loads((WEIGHTS_FOLDER / f"{person}.json").read_text())
    print(f"{person}'s weights: {saved['picks']} picks, confidence {saved['confidence']:.0%}, "
          f"saved {saved['updated']}\n")

    rows = []
    for path in sorted(p for p in Path(folder).rglob("*") if p.suffix.lower() in PHOTO_TYPES):
        result = vision.analyze(vision.decode_image(path.read_bytes()))
        if result["red_flags"]:
            rows.append((path.name, None, ", ".join(vision.RED_FLAGS[f] for f in result["red_flags"])))
        else:
            rows.append((path.name, win_chance(photo_features(result), saved), ""))

    scored = sorted((r for r in rows if r[1] is not None), key=lambda r: r[1], reverse=True)
    for name, chance, _ in scored:
        verdict = "likely pick" if chance >= LIKELY_PICK else "likely skip" if chance <= LIKELY_SKIP else "maybe"
        print(f"{name:16} {chance:5.0%}  {verdict}")
    for name, _, reason in (r for r in rows if r[1] is None):
        print(f"{name:16}   --   not scored: {reason}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
