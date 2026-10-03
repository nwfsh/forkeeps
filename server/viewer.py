"""Browse saved photos next to their measurements and detected mode.

Run from server/:  streamlit run viewer.py
"""
from pathlib import Path

import cv2
import streamlit as st

import vision

DEFAULT_FOLDER = Path(__file__).resolve().parent.parent / "data" / "training-recognition"
PHOTO_TYPES = {".jpg", ".jpeg", ".png"}
# Photos are shrunk to this width for display; the analysis still uses full size.
PREVIEW_WIDTH = 800
BOX_COLOUR = (0, 255, 0)
SKELETON_COLOUR = (255, 0, 200)
# Pose point pairs to join: shoulders, arms, torso, legs, and ear-nose-ear for the head.
SKELETON = [(11, 12), (11, 13), (13, 15), (12, 14), (14, 16), (11, 23), (12, 24), (23, 24),
            (23, 25), (25, 27), (24, 26), (26, 28), (7, 0), (0, 8)]


@st.cache_data(show_spinner=False)
def analyze_photo(path: str):
    """Analyze one photo and return a preview with face boxes drawn on, plus the result."""
    rgb = vision.decode_image(Path(path).read_bytes())
    result = vision.analyze(rgb)

    scale = PREVIEW_WIDTH / rgb.shape[1]
    preview = cv2.resize(rgb, (PREVIEW_WIDTH, round(rgb.shape[0] * scale)))
    height, width = preview.shape[:2]
    for person in result["people"]:
        points = [(int(x * width), int(y * height)) for x, y in person["points"]]
        for a, b in SKELETON:
            cv2.line(preview, points[a], points[b], SKELETON_COLOUR, 2)
        for i in (0, 7, 8):
            cv2.circle(preview, points[i], 5, SKELETON_COLOUR, -1)
    for i, face in enumerate(result["faces"]):
        b = face["bbox"]
        top_left = (int(b["x"] * width), int(b["y"] * height))
        bottom_right = (int((b["x"] + b["w"]) * width), int((b["y"] + b["h"]) * height))
        cv2.rectangle(preview, top_left, bottom_right, BOX_COLOUR, 3)
        cv2.putText(preview, str(i + 1), (top_left[0], max(20, top_left[1] - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, BOX_COLOUR, 2)
    return preview, result


def photo_mode(result: dict) -> str:
    """The first face's mode, or 'no face'."""
    return result["faces"][0].get("mode", "unknown") if result["faces"] else "no face"


def photo_view(result: dict) -> str:
    """The first person's view (front, three_quarter, profile, back), or 'no person'."""
    return result["people"][0]["view"] if result["people"] else "no person"


def tally(values: list[str]) -> dict:
    counts = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


st.set_page_config(page_title="Photo measurements", layout="wide")
st.title("Photo measurements")

folder = Path(st.sidebar.text_input("Photo folder", str(DEFAULT_FOLDER)))
paths = sorted(p for p in folder.iterdir() if p.suffix.lower() in PHOTO_TYPES) if folder.is_dir() else []
if not paths:
    st.warning(f"No photos found in {folder}")
    st.stop()

progress = st.progress(0.0)
photos = []
for i, path in enumerate(paths):
    progress.progress(i / len(paths), f"Analysing {path.name} ({i + 1}/{len(paths)})")
    photos.append((path, *analyze_photo(str(path))))
progress.empty()

mode_counts = tally([photo_mode(result) for _, _, result in photos])
view_counts = tally([photo_view(result) for _, _, result in photos])
shown_modes = st.sidebar.multiselect("Show modes", sorted(mode_counts), default=sorted(mode_counts),
                                     format_func=lambda m: f"{m} ({mode_counts[m]})")
shown_views = st.sidebar.multiselect("Show views", sorted(view_counts), default=sorted(view_counts),
                                     format_func=lambda v: f"{v} ({view_counts[v]})")
st.sidebar.caption("Change a threshold in vision.py, then press C and R here "
                   "to clear the cache and re-analyse.")


def show_table(rows: dict) -> None:
    st.table({"measurement": list(rows), "value": [str(v) for v in rows.values()]})


for path, preview, result in photos:
    mode, view = photo_mode(result), photo_view(result)
    if mode not in shown_modes or view not in shown_views:
        continue
    st.divider()
    left, right = st.columns(2)
    left.image(preview, caption=path.name)
    with right:
        st.subheader(f"{path.name} · {view} · {mode}")
        for warning in result["warnings"]:
            st.warning(warning["message"])
        for i, person in enumerate(result["people"]):
            st.markdown(f"**Body {i + 1}**" if len(result["people"]) > 1 else "**Body**")
            show_table({k: v for k, v in person.items() if k != "points"})
        for i, face in enumerate(result["faces"]):
            st.markdown(f"**Face {i + 1}**: {face.get('mode')}" if len(result["faces"]) > 1 else "**Face**")
            show_table({**face.get("measurements", {}), "cut_off": face["cut_off"]})
