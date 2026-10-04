"""See photos ranked by someone's saved weights, best first, side by side.

Run from server/:  streamlit run ranking.py
"""
import json
from pathlib import Path

import cv2
import streamlit as st

import vision
from ranker import photo_features
from score import LIKELY_PICK, LIKELY_SKIP, PHOTO_TYPES, WEIGHTS_FOLDER, win_chance

DATA = Path(__file__).resolve().parent.parent / "data" / "training-recognition"
PREVIEW_WIDTH = 400
COLUMNS = 5


@st.cache_data(show_spinner=False)
def analyze_photo(path: str, code_version: str):
    """A display-sized copy of the photo, its ranking features and its red flags."""
    rgb = vision.decode_image(Path(path).read_bytes())
    result = vision.analyze(rgb)
    scale = PREVIEW_WIDTH / rgb.shape[1]
    preview = cv2.resize(rgb, (PREVIEW_WIDTH, round(rgb.shape[0] * scale)))
    return preview, photo_features(result), result["red_flags"]


def show_grid(photos: list[tuple]) -> None:
    """Photos in rows of COLUMNS, each captioned with its rank and score."""
    for start in range(0, len(photos), COLUMNS):
        for column, (rank, path, preview, caption) in zip(st.columns(COLUMNS), photos[start:start + COLUMNS]):
            column.image(preview, caption=f"#{rank} · {path.name} · {caption}" if rank else
                         f"{path.name} · {caption}")


st.set_page_config(page_title="Photo ranking", layout="wide")
st.title("Photos ranked by your learned taste")

people = sorted(p.stem for p in WEIGHTS_FOLDER.glob("*.json"))
if not people:
    st.warning("No saved weights yet. Make picks in compare.py and open your results first.")
    st.stop()
person = st.sidebar.selectbox("Whose taste", people)
saved = json.loads((WEIGHTS_FOLDER / f"{person}.json").read_text())
default = DATA / person / "testing_data"
folder = Path(st.sidebar.text_input("Photos to rank", str(default if default.is_dir() else DATA / person)))
st.caption(f"Using {person}'s weights from {saved['picks']} picks "
           f"(confidence {saved['confidence']:.0%}). The score is the chance you'd pick the photo "
           "over an average one from your training photos.")

paths = sorted(p for p in folder.rglob("*") if p.suffix.lower() in PHOTO_TYPES) if folder.is_dir() else []
if not paths:
    st.warning(f"No photos found in {folder}")
    st.stop()

progress = st.progress(0.0)
scored, unscored = [], []
for i, path in enumerate(paths):
    progress.progress(i / len(paths), f"Analysing {path.name} ({i + 1}/{len(paths)})")
    preview, features, flags = analyze_photo(str(path), vision.code_version())
    if flags:
        unscored.append((None, path, preview, ", ".join(vision.RED_FLAGS[f] for f in flags)))
    else:
        scored.append((win_chance(features, saved), path, preview))
progress.empty()

scored.sort(key=lambda s: s[0], reverse=True)
ranked = [(rank, path, preview, chance) for rank, (chance, path, preview) in enumerate(scored, 1)]
groups = (
    ("Likely pick", [r for r in ranked if r[3] >= LIKELY_PICK]),
    ("Maybe", [r for r in ranked if LIKELY_SKIP < r[3] < LIKELY_PICK]),
    ("Likely skip", [r for r in ranked if r[3] <= LIKELY_SKIP]),
)
for title, photos in groups:
    if photos:
        st.header(f"{title} ({len(photos)})")
        show_grid([(rank, path, preview, f"{chance:.0%}") for rank, path, preview, chance in photos])
if unscored:
    st.header(f"Not scored ({len(unscored)})")
    show_grid(unscored)
