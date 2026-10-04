"""Compare the full feature set with the compact one, per person, and explain the features.

Run from server/:  streamlit run evaluate.py

Uses each person's training picks (and, if they have them, test picks) to show how well each
feature set predicts photos it wasn't trained on, what each one learned, and how each ranks the
held-back test photos. Nothing here is saved: it's a read-only report.
"""
import json
import os
from contextlib import contextmanager
from pathlib import Path

import altair as alt
import cv2
import numpy as np
import pandas as pd
import streamlit as st

import choices_db
import ranker as R
import vision

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data" / "training-recognition"
LABELS = Path(__file__).resolve().parent / "preferences" / "labels"
PHOTO_TYPES = {".jpg", ".jpeg", ".png", ".heic"}
PREVIEW_WIDTH = 220
SHOWN = 5
BAR_COLOUR = "#2a78d6"

# The compact set: features that held up on photos the model hadn't seen, for Avery and Salma.
# What each means and how it's measured, in plain words.
COMPACT = {
    "eyes_open": ("Eyes open", "1 minus the stronger eye's blink score from the face model."),
    "eye_contact": ("Looking at the camera", "1 minus how far the eyes look up, down, in or out."),
    "eye_opening": ("Eyes open wide", "Gap between the eyelids over eye width, from the face points."),
    "uneven_eyes": ("One eye more closed than the other", "Difference between the two eyes' opening."),
    "smile": ("Smiling", "Average of the left and right smile scores."),
    "teeth_shown": ("Teeth showing", "Share of the open mouth that is bright like teeth."),
    "gummy": ("Gums showing above the teeth", "Pink between the upper lip and the top edge of the teeth."),
    "expr_browDownLeft": ("Brow lowered (left)", "How far the brow is pulled down: an intense look."),
    "expr_browDownRight": ("Brow lowered (right)", "Same, other brow."),
    "expr_browInnerUp": ("Inner brows raised", "A worried or surprised lift of the inner brows."),
    "expr_mouthPressLeft": ("Lips pressed (left)", "Lips pressed together, which can bulge the lip corners."),
    "expr_mouthPressRight": ("Lips pressed (right)", "Same, other side."),
    "left_side": ("Left side toward the camera", "Head turn: positive shows the left cheek, negative the right."),
    "chin_up": ("Chin up", "Head tilt up (positive) or down (negative)."),
    "head_straight": ("Head held straight", "How close the head's side-to-side tilt is to level."),
    "v_line": ("V-line face", "Jaw narrow for the cheekbones (jaw width over cheekbone width, flipped)."),
    "chin_taper": ("Tapered chin", "Chin narrow for the jaw (chin width over jaw width, flipped)."),
    "upright": ("Head over shoulders", "How far the head sits forward of the shoulders, flipped."),
    "arms_away": ("Arms held away from the body", "Elbows' distance from the body's sides."),
    "hand_raised": ("A hand raised to the hair or head", "A wrist above shoulder height."),
    "hand_over_face": ("A hand covering part of the face", "Share of the face area the hands' outlines cover."),
    "facing_camera": ("Facing the camera", "Front, three-quarter, profile or back, as 1 to 0."),
    "body_turned": ("Body angled to the camera", "Shoulders square (0) to side-on (1)."),
}
# Plain-words explanations, for the compact set and anything active that isn't in it.
GLOSSARY = {**COMPACT, "head_tilt": ("Head tilted toward the left shoulder",
                                     "Head tilt: positive toward the left shoulder, negative the right.")}
MODELS = {
    f"Now ({len(R.FEATURES)})": (set(R.FEATURES), 1.0),
    f"Compact ({len(COMPACT)})": (set(COMPACT), 0.1),
    f"All ({len(R.ALL_FEATURES)})": (set(R.ALL_FEATURES), 1.0),
}


@contextmanager
def learning_from(features: set):
    """Have the ranker learn from these features for a while, whatever ACTIVE_FEATURES says."""
    active = R.FEATURES
    R.FEATURES = {name: R.ALL_FEATURES[name] for name in R.ALL_FEATURES if name in features}
    try:
        yield
    finally:
        R.FEATURES = active


@st.cache_data(show_spinner=False)
def analyze_photo(path: str, code_version: str):
    rgb = vision.decode_image(Path(path).read_bytes())
    result = vision.analyze(rgb)
    scale = PREVIEW_WIDTH / rgb.shape[1]
    return cv2.resize(rgb, (PREVIEW_WIDTH, round(rgb.shape[0] * scale))), R.photo_features(result), result["red_flags"]


def load(folder: Path) -> dict:
    """Photo id -> (preview, features) for the folder's photos without a red flag."""
    photos = {}
    for path in sorted(p for p in folder.rglob("*") if p.suffix.lower() in PHOTO_TYPES):
        preview, features, flags = analyze_photo(str(path), vision.code_version())
        if not flags:
            photos[os.path.relpath(path, REPO)] = (preview, features)
    return photos


def match(path: str, photos: dict) -> str:
    """A saved pick's photo, found by its path or, if the photo has since moved, by its file name."""
    if path in photos:
        return path
    by_name = [p for p in photos if Path(p).name == Path(path).name]
    return by_name[0] if len(by_name) == 1 else None


def restrict(photos: dict, keep: set) -> dict:
    """Just the features in `keep` for each photo."""
    return {p: {k: f.get(k) for k in keep} for p, (_, f) in photos.items()}


def trained(features: dict, picks: list, regularisation: float) -> R.Ranker:
    R.REGULARISATION = regularisation
    ranker = R.Ranker(features)
    ranker.fit(picks)
    return ranker


@st.cache_data(show_spinner=False)
def evaluate(person: str, code_version: str, picks: tuple, test_picks: tuple, labels: tuple) -> dict:
    """Every number on the page, for both models. Cached on the picks, so it reruns when they change."""
    train, test = load(DATA / person / "training_data"), load(DATA / person / "testing_data")
    picks, test_picks, labels = list(picks), list(test_picks), dict(labels)
    report = {}
    for name, (keep, regularisation) in MODELS.items():
        with learning_from(keep):
            tr, ts = restrict(train, keep), restrict(test, keep)
            row = {}
            # Each training pick predicted by a model trained on all the others.
            row["Training picks, each held out"] = np.mean([
                trained(tr, picks[:i] + picks[i + 1:], regularisation).win_probability(*picks[i]) > 0.5
                for i in range(len(picks))]) if picks else None
            # Each photo scored by a model that never saw a pick involving it.
            if labels:
                held = {p: trained(tr, [pk for pk in picks if p not in pk], regularisation).score_new(tr[p]) for p in labels}
                likes = [held[p] for p, lab in labels.items() if lab == "like"]
                dislikes = [held[p] for p, lab in labels.items() if lab == "dislike"]
                row["Held-out likes above dislikes"] = np.mean([a > b for a in likes for b in dislikes]) if likes and dislikes else None
            model = trained(tr, picks, regularisation)
            scores = {p: model.score_new(ts[p]) for p in ts}
            if test_picks:
                row["Test picks (new session)"] = np.mean([scores[w] > scores[l] for w, l in test_picks])
            report[name] = {"metrics": row, "priorities": model.priorities(), "regions": model.region_shares(),
                            "ranked": sorted(scores, key=scores.get, reverse=True)}
    R.REGULARISATION = 1.0
    return report


st.set_page_config(page_title="Feature evaluation", layout="wide")
st.title("Which features to learn from")

people = sorted(p.name for p in DATA.iterdir() if (p / "training_data").is_dir())
person = st.sidebar.selectbox("Whose photos", people)
with st.spinner("Analysing photos and training both models (a minute the first time)…"):
    train, test = load(DATA / person / "training_data"), load(DATA / person / "testing_data")
    picks = [(w, l) for c in choices_db.load(person)
             for w, l in [(match(c["winner"], train), match(c["loser"], train))] if w and l]
    # Like/dislike labels, kept from when photos were sorted into like/ and dislike/ folders.
    label_file = LABELS / f"{choices_db.person_key(person)}.json"
    saved_labels = json.loads(label_file.read_text()) if label_file.exists() else {}
    labels = {found: label for path, label in saved_labels.items() if (found := match(path, train))}
    test_picks = [(w, l) for c in choices_db.load_test_choices(person)
                  for w, l in [(match(c["winner"], test), match(c["loser"], test))] if w and l]
    report = evaluate(person, vision.code_version(), tuple(picks), tuple(test_picks), tuple(sorted(labels.items())))

st.caption(f"{person}: {len(train)} training photos, {len(picks)} training picks, {len(test)} test photos, "
           f"{len(test_picks)} test picks. 50% is a coin flip.")

# 1. The scores.
st.header("How well each one predicts")
metrics = pd.DataFrame({name: r["metrics"] for name, r in report.items()})
st.dataframe(metrics.style.format(lambda v: "—" if v is None or pd.isna(v) else f"{v:.0%}"))
st.markdown(
    "- **Training picks, each held out:** each pick predicted by a model trained on the rest. "
    "High for both, because it's the same photos and session.\n"
    "- **Held-out likes above dislikes:** each photo scored by a model that never saw a pick involving it; "
    "the share of like/dislike pairs it puts the right way round. The fairest test without a new session.\n"
    "- **Test picks (new session):** the weights from training picks, on picks between new photos. "
    "The real test, and what the app depends on.")
if not test_picks:
    st.info("No test picks yet. Make some in check_weights.py to see the new-session number.")

# 2. What each model learned.
st.header("What each one learned")
for column, (name, r) in zip(st.columns(len(report)), report.items()):
    with column:
        st.subheader(name)
        areas = pd.DataFrame([{"area": k, "share": v} for k, v in r["regions"].items() if v > 0.01])
        chart = alt.Chart(areas).mark_bar(color=BAR_COLOUR, cornerRadiusEnd=4, size=12).encode(
            x=alt.X("share:Q", title="Share of influence", axis=alt.Axis(format="%")),
            y=alt.Y("area:N", sort="-x", title=None))
        try:
            st.altair_chart(chart, width="stretch")
        except TypeError:
            st.altair_chart(chart, use_container_width=True)
        top = [p for p in r["priorities"] if p["varies"] and p["share"] > 0][:8]
        st.markdown("\n".join(f"{i}. **{p['prefers']}** ({p['share']:.0%})" for i, p in enumerate(top, 1)))

# 3. The test photos, as each one ranks them.
if test:
    st.header("Test photos, as each one ranks them")
    for column, (name, r) in zip(st.columns(len(report)), report.items()):
        with column:
            st.subheader(name)
            for title, photos in (("Top", r["ranked"][:SHOWN]), ("Bottom", r["ranked"][-SHOWN:][::-1])):
                st.markdown(f"**{title} {SHOWN}**")
                for cell, photo in zip(st.columns(SHOWN), photos):
                    cell.image(test[photo][0], caption=Path(photo).stem)

# 4. The features, explained.
st.header("The features it learns from now, explained")
now = {p["feature"]: p for p in next(iter(report.values()))["priorities"]}
st.dataframe(pd.DataFrame([{
    "feature": GLOSSARY.get(key, (R.FEATURES[key], ""))[0], "area": R.REGIONS[key],
    "how it's measured": GLOSSARY.get(key, ("", ""))[1],
    "learned": now[key]["prefers"] if now[key]["share"] > 0 else "no effect",
    "influence": now[key]["share"],
} for key in R.FEATURES]).sort_values("influence", ascending=False), hide_index=True,
    column_config={"influence": st.column_config.NumberColumn(format="percent")})
st.caption("Change which features are learned from in ACTIVE_FEATURES in ranker.py. Everything else is "
           "still measured for the viewer and coaching.")
