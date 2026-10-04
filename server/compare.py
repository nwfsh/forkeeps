"""Pick the better of two of your photos until the model has learned what you prioritise.

Run from server/:  streamlit run compare.py
"""
import json
import os
import random
import re
from datetime import datetime, timezone
from pathlib import Path

import altair as alt
import cv2
import pandas as pd
import streamlit as st

import vision
from ranker import CLEAR, LIKELY, MAX_CHOICES, MIN_CHOICES, RECENT_GUESSES, Ranker, photo_features

REPO = Path(__file__).resolve().parent.parent
DEFAULT_FOLDER = REPO / "data" / "training-recognition"
CHOICES_FOLDER = Path(__file__).resolve().parent / "preferences"
PHOTO_TYPES = {".jpg", ".jpeg", ".png"}
PREVIEW_WIDTH = 700
SHOWN_PHOTOS = 5
# How many priorities the results spell out in words.
SHOWN_PRIORITIES = 3
BAR_COLOUR = "#2a78d6"


@st.cache_data(show_spinner=False)
def analyze_photo(path: str):
    """A display-sized copy of the photo and its ranking features."""
    rgb = vision.decode_image(Path(path).read_bytes())
    features = photo_features(vision.analyze(rgb))
    scale = PREVIEW_WIDTH / rgb.shape[1]
    preview = cv2.resize(rgb, (PREVIEW_WIDTH, round(rgb.shape[0] * scale)))
    return preview, features


def photo_paths(folder: Path) -> list[Path]:
    """Every photo in the folder, including subfolders such as like/ and dislike/."""
    return sorted(p for p in folder.rglob("*") if p.suffix.lower() in PHOTO_TYPES)


def photo_id(path: Path) -> str:
    """The photo's path from the repo root, so choices still match if the folder setting changes."""
    return os.path.relpath(path, REPO)


def choices_file(name: str) -> Path:
    """Where one person's choices are saved."""
    return CHOICES_FOLDER / f"{re.sub(r'[^A-Za-z0-9_-]', '', name) or 'me'}.json"


def load_choices(name: str) -> list[dict]:
    path = choices_file(name)
    return json.loads(path.read_text()) if path.exists() else []


def save_choices(name: str, choices: list[dict]) -> None:
    CHOICES_FOLDER.mkdir(exist_ok=True)
    choices_file(name).write_text(json.dumps(choices, indent=1))


def pick(name: str, winner: str, loser: str, winner_probability) -> None:
    """Record a choice, noting whether the model (before seeing it) would have guessed it."""
    choices = load_choices(name)
    choices.append({
        "winner": winner,
        "loser": loser,
        "model_agreed": None if winner_probability is None else winner_probability > 0.5,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    save_choices(name, choices)
    st.session_state.pair = None


def skip(a: str, b: str) -> None:
    st.session_state.skipped.add(frozenset((a, b)))
    st.session_state.pair = None


def set_view(name: str, view: str) -> None:
    """Show this person's results, or keep comparing even though the results are ready."""
    st.session_state.view[name] = view


def start_over(name: str) -> None:
    save_choices(name, [])
    st.session_state.view.pop(name, None)
    st.session_state.skipped = set()
    st.session_state.pair = None


def undo(name: str) -> None:
    choices = load_choices(name)
    if choices:
        last = choices.pop()
        save_choices(name, choices)
        st.session_state.pair = (last["winner"], last["loser"])
        st.session_state.view.pop(name, None)


st.set_page_config(page_title="Photo duel", layout="wide")
st.session_state.setdefault("pair", None)
st.session_state.setdefault("skipped", set())
st.session_state.setdefault("rng", random.Random())
# Per person: "results" once they ask to see them, "comparing" once they choose to keep going.
st.session_state.setdefault("view", {})

folder = Path(st.sidebar.text_input("Photo folder", str(DEFAULT_FOLDER),
                                     help="One subfolder of photos per person."))
# Each person only compares their own photos, and their choices are kept separately.
people = {sub.name: photo_paths(sub) for sub in sorted(folder.iterdir()) if sub.is_dir()} \
    if folder.is_dir() else {}
people = {person: paths for person, paths in people.items() if len(paths) >= 2}
if not people:
    st.warning(f"No subfolder of {folder} has at least two photos")
    st.stop()
name = st.sidebar.selectbox("Whose photos", list(people),
                            format_func=lambda person: f"{person} ({len(people[person])} photos)")
paths = people[name]

progress = st.progress(0.0)
previews, features = {}, {}
for i, path in enumerate(paths):
    progress.progress(i / len(paths), f"Analysing {path.name} ({i + 1}/{len(paths)})")
    previews[photo_id(path)], features[photo_id(path)] = analyze_photo(str(path))
progress.empty()


choices = load_choices(name)
pairs = [(c["winner"], c["loser"]) for c in choices]
ranker = Ranker(features)
ranker.fit(pairs)
stop = ranker.stop_reason(choices)
view = st.session_state.view.get(name)
showing_results = view == "results" or (stop is not None and view != "comparing")

st.sidebar.metric("Picks made", len(choices))
st.sidebar.button("Undo last pick", on_click=undo, args=(name,), disabled=not choices)
with st.sidebar.popover("Start over", disabled=not choices):
    st.write(f"This deletes all {len(choices)} of {name}'s picks.")
    st.button("Delete my picks", type="primary", on_click=start_over, args=(name,))
st.sidebar.caption(f"Saved to {choices_file(name).relative_to(REPO)}")


def show_comparison() -> None:
    count = len(choices)
    if stop is not None:
        status = "Extra picks: your results update as you go"
    elif count < MIN_CHOICES:
        status = f"{count} picks · results after {MIN_CHOICES}"
    else:
        status = f"{count} picks · stopping once your pattern is clear (at most {MAX_CHOICES})"
    st.progress(min(1.0, count / MAX_CHOICES), text=status)

    pair = st.session_state.pair
    if pair is None or not all(p in features for p in pair):
        seen = {frozenset(p) for p in pairs} | st.session_state.skipped
        pair = st.session_state.pair = ranker.next_pair(seen, st.session_state.rng)
    if pair is None:
        st.success("You've compared every pair of photos.")
        st.button("See my results", type="primary", on_click=set_view, args=(name, "results"))
        return

    a, b = pair
    st.subheader("Which photo do you like more?")
    st.caption("Go with your gut. There are no wrong answers.")
    probability = ranker.win_probability(a, b) if ranker.weights.any() else None
    for column, (shown, other) in zip(st.columns(2), ((a, b), (b, a))):
        column.image(previews[shown], width="stretch")
        column.button("This one", key=f"pick-{shown}", width="stretch", type="primary",
                      on_click=pick, args=(name, shown, other,
                                           None if probability is None
                                           else probability if shown == a else 1 - probability))
    left, right = st.columns(2)
    left.button("Can't decide", on_click=skip, args=(a, b), width="stretch")
    if count >= MIN_CHOICES:
        right.button("Show my results now", on_click=set_view, args=(name, "results"), width="stretch")


def show_results() -> None:
    count = len(choices)
    st.header("What you look for in a photo")
    guesses = [c["model_agreed"] for c in choices[-RECENT_GUESSES:] if c["model_agreed"] is not None]
    why = {
        "predictable": f"it guessed {sum(guesses)} of your last {len(guesses)} picks before you made them",
        "clear": "your top priority stayed the same however your picks were reshuffled",
        "limit": "that's the most it asks for",
    }
    st.caption(f"Based on {count} picks" + (f": {why[stop]}." if stop else "."))

    sure = ranker.confidence(pairs)
    if sure >= CLEAR:
        st.success("**Clear pattern.** Your top priority holds up however your picks are reshuffled.")
    elif sure >= LIKELY:
        st.info("**Likely pattern.** A few more picks would firm it up.")
    else:
        st.warning("**No clear pattern yet.** Your picks may depend on things this can't measure, "
                   "like lighting, outfit or background. Treat these as rough.")

    rows = pd.DataFrame(ranker.priorities())
    rows["direction"] = rows["weight"].map(lambda w: "more" if w > 0 else "less")
    rows["name"] = rows["label"] + " (" + rows["direction"] + ")"
    same_everywhere = rows.loc[~rows["varies"], "label"].tolist()
    rows = rows[rows["varies"] & (rows["share"] > 0)]

    st.subheader("You tend to pick photos with…")
    for _, row in rows.head(SHOWN_PRIORITIES).iterrows():
        st.markdown(f"- **{row['label']}**, {'more' if row['weight'] > 0 else 'less'} of it")

    chart = alt.Chart(rows).mark_bar(color=BAR_COLOUR, cornerRadiusEnd=4, size=14).encode(
        x=alt.X("share:Q", title="Share of influence on your picks", axis=alt.Axis(format="%")),
        y=alt.Y("name:N", sort="-x", title=None, axis=alt.Axis(labelLimit=320)),
        tooltip=[alt.Tooltip("label:N", title="Feature"),
                 alt.Tooltip("direction:N", title="You prefer"),
                 alt.Tooltip("share:Q", title="Share", format=".0%"),
                 alt.Tooltip("weight:Q", title="Weight", format=".2f")],
    )
    st.altair_chart(chart, width="stretch")
    if same_everywhere:
        st.caption("Not ranked because they're the same in every photo here: "
                   + ", ".join(same_everywhere).lower())
    with st.expander("As a table"):
        st.dataframe(rows[["label", "direction", "share", "weight"]], hide_index=True,
                     column_config={"direction": "you prefer",
                                    "share": st.column_config.NumberColumn(format="percent"),
                                    "weight": st.column_config.NumberColumn(format="%.2f")})

    scores = ranker.scores()
    ranked = sorted(scores, key=scores.get, reverse=True)
    for title, shown in (("Photos it thinks you'd like most", ranked[:SHOWN_PHOTOS]),
                         ("…and least", ranked[-SHOWN_PHOTOS:][::-1])):
        st.subheader(title)
        for column, photo in zip(st.columns(SHOWN_PHOTOS), shown):
            column.image(previews[photo], width="stretch")

    st.button("Keep going", on_click=set_view, args=(name, "comparing"),
              help="More picks sharpen the results.")


if showing_results:
    show_results()
else:
    show_comparison()
