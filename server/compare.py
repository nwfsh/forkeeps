"""Pick the better of two of your photos until the model has learned what you prioritise.

Run from server/:  streamlit run compare.py
"""
import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path

import altair as alt
import cv2
import pandas as pd
import streamlit as st

import choices_db
import vision
from ranker import CLEAR, LIKELY, MAX_CHOICES, MIN_CHOICES, RECENT_GUESSES, Ranker, photo_features

REPO = Path(__file__).resolve().parent.parent
DEFAULT_FOLDER = REPO / "data" / "training-recognition"
WEIGHTS_FOLDER = Path(__file__).resolve().parent / "preferences" / "weights"
PHOTO_TYPES = {".jpg", ".jpeg", ".png"}
# Subfolder of held-back photos the weights are tested on, never compared.
HELD_OUT = "testing_data"
PREVIEW_WIDTH = 700
SHOWN_PHOTOS = 5
# How many priorities the results spell out in words.
SHOWN_PRIORITIES = 3
BAR_COLOUR = "#2a78d6"
# The per-feature chart shows this many; the table under it lists them all.
DETAIL_BARS = 20


@st.cache_data(show_spinner=False)
def analyze_photo(path: str, code_version: str):
    """A display-sized copy of the photo, its ranking features and its red flags."""
    rgb = vision.decode_image(Path(path).read_bytes())
    result = vision.analyze(rgb)
    scale = PREVIEW_WIDTH / rgb.shape[1]
    preview = cv2.resize(rgb, (PREVIEW_WIDTH, round(rgb.shape[0] * scale)))
    return preview, photo_features(result), result["red_flags"]


def photo_paths(folder: Path) -> list[Path]:
    """Every photo in the folder, including subfolders such as like/ and dislike/.

    Photos in a testing_data/ folder are held back to check the learned weights on photos
    they weren't trained on (see score.py), so they're never shown here.
    """
    return sorted(p for p in folder.rglob("*") if p.suffix.lower() in PHOTO_TYPES
                  and HELD_OUT not in p.relative_to(folder).parts)


def photo_id(path: Path) -> str:
    """The photo's path from the repo root, so choices still match if the folder setting changes.

    Always with forward slashes, so picks match across Windows and Mac.
    """
    return Path(os.path.relpath(path, REPO)).as_posix()


def pick(name: str, winner: str, loser: str, winner_probability) -> None:
    """Record a choice, noting whether the model (before seeing it) would have guessed it."""
    choices_db.add(name, winner, loser, None if winner_probability is None else winner_probability > 0.5)
    st.session_state.pair = None


def skip(a: str, b: str) -> None:
    st.session_state.skipped.add(frozenset((a, b)))
    st.session_state.pair = None


def set_view(name: str, view: str) -> None:
    """Show this person's results, or keep comparing even though the results are ready."""
    st.session_state.view[name] = view


def start_over(name: str) -> None:
    choices_db.clear(name)
    st.session_state.view.pop(name, None)
    st.session_state.skipped = set()
    st.session_state.pair = None


def undo(name: str) -> None:
    last = choices_db.remove_last(name)
    if last:
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
previews, features, flags = {}, {}, {}
for i, path in enumerate(paths):
    progress.progress(i / len(paths), f"Analysing {path.name} ({i + 1}/{len(paths)})")
    previews[photo_id(path)], features[photo_id(path)], flags[photo_id(path)] = analyze_photo(str(path), vision.code_version())
progress.empty()

# Photos whose measurements can't be trusted are left out, so they don't teach the ranker
# anything false. Bad-but-measurable photos (a blink, an awkward crop) stay in.
flag_counts = {code: sum(code in f for f in flags.values()) for code in vision.RED_FLAGS}
raised = [code for code in vision.RED_FLAGS if flag_counts[code]]
leave_out = st.sidebar.multiselect(
    "Leave out photos with", raised, default=raised,
    format_func=lambda code: f"{vision.RED_FLAGS[code]} ({flag_counts[code]})",
    help="These photos can't be measured reliably, so picks involving them would mislead the model.")
left_out = {photo: f for photo, f in flags.items() if set(f) & set(leave_out)}
if left_out:
    with st.sidebar.expander(f"{len(left_out)} of {len(flags)} photos left out"):
        for photo, f in left_out.items():
            st.image(previews[photo], caption=", ".join(vision.RED_FLAGS[code] for code in f))
features = {photo: v for photo, v in features.items() if photo not in left_out}
if len(features) < 2:
    st.warning("Fewer than two photos are left to compare. Leave out fewer kinds of photo in the sidebar.")
    st.stop()


# Picks about photos that have since been moved or deleted can't teach anything, and
# counting them would end the comparing early.
saved_choices = choices_db.load(name)
choices = [c for c in saved_choices if c["winner"] in features and c["loser"] in features]
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
st.sidebar.caption(f"Saved to {choices_db.DB_PATH.relative_to(REPO).as_posix()}")
if len(saved_choices) > len(choices):
    st.sidebar.caption(f"{len(saved_choices) - len(choices)} older picks are about photos that aren't "
                       "here any more, so they're ignored.")


def save_weights(person: str, picks: int, confidence: float) -> Path:
    """Keep this person's learned weights in the database's history, and write the latest to a
    JSON file the app can score new photos with. Neither changes if the weights haven't."""
    path = WEIGHTS_FOLDER / f"{choices_db.person_key(person)}.json"
    export = ranker.export()
    if choices_db.save_weights(person, picks, round(confidence, 2), export) or not path.exists():
        WEIGHTS_FOLDER.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "person": person,
            "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "picks": picks,
            "confidence": round(confidence, 2),
            **export,
        }, indent=1))
    return path


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

    sure = ranker.region_confidence(pairs)
    if sure >= CLEAR:
        st.success("**Clear pattern.** The area that matters most to you holds up however your picks are reshuffled.")
    elif sure >= LIKELY:
        st.info("**Likely pattern.** A few more picks would firm it up.")
    else:
        st.warning("**No clear pattern yet.** Your picks may depend on things this can't measure, "
                   "like outfit, background or setting. Treat these as rough.")

    rows = pd.DataFrame(ranker.priorities())
    saved = save_weights(name, count, sure)

    st.subheader("What matters most, by area")
    areas = pd.DataFrame([{"region": r, "share": v} for r, v in ranker.region_shares().items() if v > 0])
    area_chart = alt.Chart(areas).mark_bar(color=BAR_COLOUR, cornerRadiusEnd=4, size=14).encode(
        x=alt.X("share:Q", title="Share of how much your picks depend on it", axis=alt.Axis(format="%")),
        y=alt.Y("region:N", sort="-x", title=None),
        tooltip=[alt.Tooltip("region:N", title="Area"), alt.Tooltip("share:Q", title="Share", format=".0%")],
    )
    try:
        st.altair_chart(area_chart, width="stretch")
    except TypeError:
        st.altair_chart(area_chart, use_container_width=True)
    same_everywhere = rows.loc[~rows["varies"], "label"].tolist()
    rows = rows[rows["varies"] & (rows["share"] > 0)]

    st.subheader("You tend to pick photos with…")
    for _, row in rows.head(SHOWN_PRIORITIES).iterrows():
        st.markdown(f"- **{row['prefers']}**")

    st.subheader(f"Top {DETAIL_BARS} details")
    chart = alt.Chart(rows.head(DETAIL_BARS)).mark_bar(color=BAR_COLOUR, cornerRadiusEnd=4, size=14).encode(
        x=alt.X("share:Q", title="Share of influence on your picks", axis=alt.Axis(format="%")),
        y=alt.Y("prefers:N", sort="-x", title=None, axis=alt.Axis(labelLimit=320)),
        tooltip=[alt.Tooltip("label:N", title="Feature"),
                 alt.Tooltip("prefers:N", title="You prefer"),
                 alt.Tooltip("share:Q", title="Share", format=".0%"),
                 alt.Tooltip("weight:Q", title="Weight", format=".2f")],
    )
    try:
        st.altair_chart(chart, width="stretch")
    except TypeError:
        # Streamlit 1.50, the last release for Python 3.9, has no width option on charts yet.
        st.altair_chart(chart, use_container_width=True)
    if same_everywhere:
        st.caption("Not ranked because they're the same in every photo here: "
                   + ", ".join(same_everywhere).lower())
    with st.expander("As a table"):
        st.dataframe(rows[["region", "label", "prefers", "share", "weight"]], hide_index=True,
                     column_config={"prefers": "you prefer",
                                    "share": st.column_config.NumberColumn(format="percent"),
                                    "weight": st.column_config.NumberColumn(format="%.2f")})

    history = choices_db.weights_history(name)
    st.caption(f"Weights saved to {saved.relative_to(REPO).as_posix()} and the database "
               f"({len(history)} version{'' if len(history) == 1 else 's'} so far)")
    if len(history) > 1:
        with st.expander("How your results have changed"):
            st.dataframe(pd.DataFrame([{
                "saved": h["saved_at"].replace("T", " ")[:16], "picks": h["picks"],
                "confidence": h["confidence"],
                "top area": max(h["regions"], key=h["regions"].get) if h.get("regions") else None,
            } for h in reversed(history)]), hide_index=True,
                column_config={"confidence": st.column_config.NumberColumn(format="percent")})

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
