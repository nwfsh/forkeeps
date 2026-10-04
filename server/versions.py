"""Compare two versions of the ranker on held-back photos, side by side.

Run from server/:  streamlit run versions.py

Both versions learn from the same picks on the person's training photos. "Before" uses the
features from before the full face mapping; "Full face" adds all 52 expression scores. Mark
your own favourites and least favourites in the sidebar to see which version agrees with you more.
"""
import os
from pathlib import Path

import cv2
import numpy as np
import streamlit as st

import choices_db
import vision
from ranker import FEATURES, Ranker, photo_features

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data" / "training-recognition"
PHOTO_TYPES = {".jpg", ".jpeg", ".png"}
PREVIEW_WIDTH = 300


@st.cache_data(show_spinner=False)
def analyze_photo(path: str, code_version: str):
    rgb = vision.decode_image(Path(path).read_bytes())
    result = vision.analyze(rgb)
    scale = PREVIEW_WIDTH / rgb.shape[1]
    return cv2.resize(rgb, (PREVIEW_WIDTH, round(rgb.shape[0] * scale))), photo_features(result), result["red_flags"]


def load(folder: Path) -> dict:
    """Photo id -> (preview, features), skipping red-flagged photos."""
    photos = {}
    for path in sorted(p for p in folder.rglob("*") if p.suffix.lower() in PHOTO_TYPES):
        preview, features, flags = analyze_photo(str(path), vision.code_version())
        if not flags:
            # Forward slashes on every OS, to match the saved picks.
            photos[Path(os.path.relpath(path, REPO)).as_posix()] = (preview, features)
    return photos


def without_face_detail(features: dict) -> dict:
    """The features as before the full face mapping: every expression score left out."""
    return {name: (0.0 if name.startswith("expr_") else value) for name, value in features.items()}


def train_and_score(train: dict, test: dict, picks: list, full_face: bool) -> tuple[dict, float]:
    """Each test photo's chance of beating an average training photo, and the confidence."""
    prepare = (lambda f: f) if full_face else without_face_detail
    ranker = Ranker({photo: prepare(f) for photo, (_, f) in train.items()})
    ranker.fit(picks)
    scores = {}
    for photo, (_, f) in test.items():
        f = prepare(f)
        x = np.array([ranker.mean[i] if f.get(name) is None else f[name] for i, name in enumerate(FEATURES)])
        scores[photo] = float(1 / (1 + np.exp(-(ranker.weights @ ((x - ranker.mean) / ranker.std)))))
    return scores, ranker.region_confidence(picks)


def agreement(scores: dict, liked: list, disliked: list) -> str:
    """Share of (favourite, least favourite) pairs the version orders the same way you do."""
    pairs = [(a, b) for a in liked for b in disliked]
    if not pairs:
        return "mark favourites and least favourites to compare"
    right = sum(scores[a] > scores[b] for a, b in pairs)
    return f"agrees with you on {right} of {len(pairs)} pairs ({right / len(pairs):.0%})"


st.set_page_config(page_title="Ranker versions", layout="wide")
st.title("Before vs full face detail")

person = st.sidebar.selectbox("Whose photos", sorted(p.name for p in DATA.iterdir() if (p / "testing_data").is_dir()))
with st.spinner("Analysing training and test photos (about 30 seconds the first time)…"):
    train, test = load(DATA / person / "training_data"), load(DATA / person / "testing_data")
picks = [(c["winner"], c["loser"]) for c in choices_db.load(person)
         if c["winner"] in train and c["loser"] in train]
if not picks:
    st.warning("No picks on the training photos yet. Make some in compare.py first.")
    st.stop()

name = lambda photo: Path(photo).stem
liked = st.sidebar.multiselect("Your favourites", sorted(test), format_func=name)
disliked = st.sidebar.multiselect("Your least favourites", sorted(set(test) - set(liked)), format_func=name)
st.caption(f"Both trained on {len(picks)} picks of {len(train)} training photos, "
           f"ranking {len(test)} test photos. Pick your favourites before looking, to keep it fair.")

for column, (title, full_face) in zip(st.columns(2), (("Before: no face detail", False), ("Full face detail", True))):
    scores, confidence = train_and_score(train, test, picks, full_face)
    ranked = sorted(scores, key=scores.get, reverse=True)
    with column:
        st.header(title)
        st.markdown(f"Confidence **{confidence:.0%}** · {agreement(scores, liked, disliked)}")
        for start in range(0, len(ranked), 3):
            for cell, photo in zip(st.columns(3), ranked[start:start + 3]):
                mark = " ★" if photo in liked else " ✗" if photo in disliked else ""
                cell.image(test[photo][0], caption=f"#{ranked.index(photo) + 1} {name(photo)} · {scores[photo]:.0%}{mark}")
