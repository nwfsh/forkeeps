"""Browse saved photos next to their measurements and detected mode.

Run from server/:  streamlit run viewer.py
"""
from pathlib import Path

import cv2
import streamlit as st

import vision
from ranker import expression_region as ranker_region

DEFAULT_FOLDER = Path(__file__).resolve().parent.parent / "data" / "training-recognition"
PHOTO_TYPES = {".jpg", ".jpeg", ".png"}
# Photos are shrunk to this width for display; the analysis still uses full size.
PREVIEW_WIDTH = 800
BOX_COLOUR = (0, 255, 0)
SKELETON_COLOUR = (255, 0, 200)
# Pose point pairs to join: shoulders, arms, torso, legs, and ear-nose-ear for the head.
# Face close-ups: padding around the face box, display width, and colours per region.
FACE_PADDING = 0.25
CLOSEUP_WIDTH = 480
MESH_COLOUR = (120, 120, 120)
REGION_COLOURS = {"Face oval": (230, 230, 230), "Brows": (255, 170, 0), "Eyes": (0, 200, 255),
                  "Irises": (40, 90, 255), "Nose": (190, 120, 255), "Mouth": (255, 60, 120)}
SKELETON = [(11, 12), (11, 13), (13, 15), (12, 14), (14, 16), (11, 23), (12, 24), (23, 24),
            (23, 25), (25, 27), (24, 26), (26, 28), (7, 0), (0, 8)]


@st.cache_data(show_spinner=False)
def analyze_photo(path: str, code_version: str):
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


@st.cache_data(show_spinner=False)
def face_closeups(path: str, faces: list) -> list:
    """A close-up of each face with all 478 face points drawn, outlines coloured by region."""
    rgb = vision.decode_image(Path(path).read_bytes())
    height, width = rgb.shape[:2]
    closeups = []
    for face in faces:
        b = face["bbox"]
        pad_x, pad_y = b["w"] * FACE_PADDING, b["h"] * FACE_PADDING
        x0, y0 = max(0, int((b["x"] - pad_x) * width)), max(0, int((b["y"] - pad_y) * height))
        x1 = min(width, int((b["x"] + b["w"] + pad_x) * width))
        y1 = min(height, int((b["y"] + b["h"] + pad_y) * height))
        scale = CLOSEUP_WIDTH / (x1 - x0)
        crop = cv2.resize(rgb[y0:y1, x0:x1], (CLOSEUP_WIDTH, round((y1 - y0) * scale)))
        points = [(int((x * width - x0) * scale), int((y * height - y0) * scale)) for x, y, _ in face["landmarks"]]
        for a, c in vision.FACE_MESH:
            cv2.line(crop, points[a], points[c], MESH_COLOUR, 1, cv2.LINE_AA)
        for region, edges in vision.LANDMARK_REGIONS.items():
            for a, c in edges:
                cv2.line(crop, points[a], points[c], REGION_COLOURS[region], 2, cv2.LINE_AA)
        closeups.append(crop)
    return closeups


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
# Each subfolder is one person's photos (avery, salma, sarah, ...).
people_folders = sorted(p.name for p in folder.iterdir() if p.is_dir()) if folder.is_dir() else []
chosen = st.sidebar.selectbox("Person", people_folders + ["all"]) if people_folders else "all"
search = folder if chosen == "all" else folder / chosen
paths = sorted(p for p in search.rglob("*") if p.suffix.lower() in PHOTO_TYPES) if search.is_dir() else []
if not paths:
    st.warning(f"No photos found in {search}")
    st.stop()

progress = st.progress(0.0)
photos = []
for i, path in enumerate(paths):
    progress.progress(i / len(paths), f"Analysing {path.name} ({i + 1}/{len(paths)})")
    photos.append((path, *analyze_photo(str(path), vision.code_version())))
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
    left.image(preview, caption=str(path.relative_to(folder)))
    with right:
        st.subheader(f"{path.relative_to(folder)} · {view} · {mode}")
        for warning in result["warnings"]:
            st.warning(warning["message"])
        for i, person in enumerate(result["people"]):
            st.markdown(f"**Body {i + 1}**" if len(result["people"]) > 1 else "**Body**")
            show_table({k: v for k, v in person.items() if k != "points"})
        closeups = face_closeups(str(path), result["faces"]) if result["faces"] else []
        for i, (face, closeup) in enumerate(zip(result["faces"], closeups)):
            st.markdown(f"**Face {i + 1}**: {face.get('mode')}" if len(result["faces"]) > 1 else "**Face**")
            show_table({**face.get("measurements", {}), "cut_off": face["cut_off"]})
            if face.get("lighting"):
                with st.expander("Lighting and contour"):
                    show_table(face["lighting"])
            st.image(closeup, caption=f"All {len(face['landmarks'])} face points; outlines: "
                     + ", ".join(vision.LANDMARK_REGIONS))
            by_region = {}
            for name, score in face.get("expressions", {}).items():
                by_region.setdefault(ranker_region(name), {})[name] = score
            for region, scores in by_region.items():
                with st.expander(f"{region}: {len(scores)} expression scores"):
                    show_table(dict(sorted(scores.items(), key=lambda kv: -kv[1])))
