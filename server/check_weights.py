"""Pick the better of two held-back test photos, then see how often your learned weights agree.

Run from server/:  streamlit run check_weights.py

Works like compare.py, but on the photos in <person>/testing_data/, and the picks are saved to
the test_choices table: they're never used for training, only to check the weights learned
from your training picks against photos those weights have never seen. Pairs are random
rather than chosen by the model, and no scores are shown, so neither can sway the test.
"""
import os
import random
from pathlib import Path

import cv2
import streamlit as st

import choices_db
import vision
from ranker import Ranker, photo_features

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data" / "training-recognition"
PHOTO_TYPES = {".jpg", ".jpeg", ".png", ".heic"}
PREVIEW_WIDTH = 700
# Test picks needed before the agreement is shown; fewer would be mostly luck.
MIN_TEST_PICKS = 10


@st.cache_data(show_spinner=False)
def analyze_photo(path: str, code_version: str):
    """A display-sized copy of the photo, its ranking features and its red flags."""
    rgb = vision.decode_image(Path(path).read_bytes())
    result = vision.analyze(rgb)
    scale = PREVIEW_WIDTH / rgb.shape[1]
    preview = cv2.resize(rgb, (PREVIEW_WIDTH, round(rgb.shape[0] * scale)))
    return preview, photo_features(result), result["red_flags"]


def load(folder: Path) -> dict:
    """Photo id -> (preview, features) for every photo in the folder without a red flag."""
    photos = {}
    for path in sorted(p for p in folder.rglob("*") if p.suffix.lower() in PHOTO_TYPES):
        preview, features, flags = analyze_photo(str(path), vision.code_version())
        if not flags:
            photos[os.path.relpath(path, REPO)] = (preview, features)
    return photos


def pick(person: str, winner: str, loser: str) -> None:
    choices_db.add_test_choice(person, winner, loser)
    st.session_state.pair = None


def skip(a: str, b: str) -> None:
    st.session_state.skipped.add(frozenset((a, b)))
    st.session_state.pair = None


def clear_tests(person: str) -> None:
    choices_db.clear_test_choices(person)
    st.session_state.skipped = set()
    st.session_state.pair = None


def undo(person: str) -> None:
    last = choices_db.remove_last_test_choice(person)
    if last:
        st.session_state.pair = (last["winner"], last["loser"])


st.set_page_config(page_title="Test your weights", layout="wide")
st.session_state.setdefault("pair", None)
st.session_state.setdefault("skipped", set())
st.session_state.setdefault("rng", random.Random())
st.title("Test your weights")

people = sorted(p.name for p in DATA.iterdir()
                if (p / "testing_data").is_dir() and (p / "training_data").is_dir())
if not people:
    st.warning("No one has both a training_data and a testing_data folder yet.")
    st.stop()
person = st.sidebar.selectbox("Whose photos", people)

with st.spinner("Analysing training and test photos (about 30 seconds the first time)…"):
    train, test = load(DATA / person / "training_data"), load(DATA / person / "testing_data")
def match(path: str, photos: dict):
    """A saved pick's photo, found by its path or, if the photo has since moved, by its file name."""
    if path in photos:
        return path
    by_name = [p for p in photos if Path(p).name == Path(path).name]
    return by_name[0] if len(by_name) == 1 else None


training_picks = [(w, l) for c in choices_db.load(person)
                  for w, l in [(match(c["winner"], train), match(c["loser"], train))] if w and l]
test_choices = [c for c in choices_db.load_test_choices(person) if c["winner"] in test and c["loser"] in test]

# The weights as they stand from the training picks only.
ranker = Ranker({photo: f for photo, (_, f) in train.items()})
ranker.fit(training_picks)
scores = {photo: ranker.score_new(f) for photo, (_, f) in test.items()}
agreed = [scores[c["winner"]] > scores[c["loser"]] for c in test_choices]

st.sidebar.metric("Test picks made", len(test_choices))
st.sidebar.caption(f"Weights learned from {len(training_picks)} training picks. "
                   "Test picks are never used for training.")
st.sidebar.button("Undo last pick", on_click=undo, args=(person,), disabled=not test_choices)
with st.sidebar.popover("Start over", disabled=not test_choices):
    st.write(f"This deletes all {len(test_choices)} of {person}'s test picks.")
    st.button("Delete my test picks", type="primary", on_click=clear_tests, args=(person,))

if not training_picks:
    st.warning("No training picks yet, so there are no weights to test. Make some in compare.py first.")
elif len(test_choices) < MIN_TEST_PICKS:
    st.info(f"Make at least {MIN_TEST_PICKS} test picks to see how well your weights match "
            f"({len(test_choices)} so far).")
else:
    rate = sum(agreed) / len(agreed)
    verdict = ("they've learned your taste well" if rate >= 0.8 else
               "they've learned something real about your taste" if rate >= 0.65 else
               "no better than a coin flip yet" if rate <= 0.55 else "a weak match so far")
    st.success(f"Your weights picked the same photo as you in **{sum(agreed)} of {len(agreed)}** test picks "
               f"(**{rate:.0%}**; a coin flip gets 50%): {verdict}.")
    with st.expander("Where they disagreed with you"):
        misses = [c for c, ok in zip(test_choices, agreed) if not ok]
        if not misses:
            st.write("Nowhere yet.")
        for c in misses:
            chosen, other = st.columns(2)
            chosen.image(test[c["winner"]][0], caption=f"You picked {Path(c['winner']).stem}")
            other.image(test[c["loser"]][0], caption=f"The weights preferred {Path(c['loser']).stem}")

# A random pair you haven't compared or skipped yet.
pair = st.session_state.pair
if pair is None or not all(p in test for p in pair):
    done = {frozenset((c["winner"], c["loser"])) for c in test_choices} | st.session_state.skipped
    remaining = [(a, b) for i, a in enumerate(sorted(test)) for b in sorted(test)[i + 1:]
                 if frozenset((a, b)) not in done]
    # Shuffled once, so which photo is on the left doesn't follow the file names.
    pair = st.session_state.pair = (tuple(st.session_state.rng.sample(st.session_state.rng.choice(remaining), 2))
                                    if remaining else None)
if pair is None:
    st.success("You've compared every pair of test photos.")
    st.stop()

a, b = pair
st.subheader("Which photo do you like more?")
st.caption("Go with your gut. These picks only test your weights; they don't train them.")
for column, (shown, other) in zip(st.columns(2), ((a, b), (b, a))):
    column.image(test[shown][0], width="stretch")
    column.button("This one", key=f"pick-{shown}", width="stretch", type="primary",
                  on_click=pick, args=(person, shown, other))
st.button("Can't decide", on_click=skip, args=(a, b))
