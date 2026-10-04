"""Browse saved photos next to their measurements and detected mode.

Run from server/:  streamlit run viewer.py
"""
from pathlib import Path

import cv2
import numpy as np
import streamlit as st

import vision
from ranker import expression_region as ranker_region

DEFAULT_FOLDER = Path(__file__).resolve().parent.parent / "data" / "training-recognition"
PHOTO_TYPES = {".jpg", ".jpeg", ".png", ".heic"}
# Photos are shrunk to this width for display; the analysis still uses full size.
PREVIEW_WIDTH = 800
BOX_COLOUR = (0, 255, 0)
SKELETON_COLOUR = (255, 0, 200)
# Face close-ups: padding around the face box, display width, and colours per region.
FACE_PADDING = 0.25
CLOSEUP_WIDTH = 480
MESH_COLOUR = (120, 120, 120)
REGION_COLOURS = {"Face oval": (230, 230, 230), "Brows": (255, 170, 0), "Eyes": (0, 200, 255),
                  "Irises": (40, 90, 255), "Nose": (190, 120, 255), "Mouth": (255, 60, 120)}
SWATCH_SIZE = 90
# Pose point pairs to join: shoulders, arms, torso, legs, and ear-nose-ear for the head.
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


def face_crop(rgb, face: dict) -> tuple:
    """The face, padded and resized to CLOSEUP_WIDTH, with its 478 points in the crop's pixels."""
    height, width = rgb.shape[:2]
    b = face["bbox"]
    pad_x, pad_y = b["w"] * FACE_PADDING, b["h"] * FACE_PADDING
    x0, y0 = max(0, int((b["x"] - pad_x) * width)), max(0, int((b["y"] - pad_y) * height))
    x1 = min(width, int((b["x"] + b["w"] + pad_x) * width))
    y1 = min(height, int((b["y"] + b["h"] + pad_y) * height))
    scale = CLOSEUP_WIDTH / (x1 - x0)
    crop = cv2.resize(rgb[y0:y1, x0:x1], (CLOSEUP_WIDTH, round((y1 - y0) * scale)))
    points = [(int((x * width - x0) * scale), int((y * height - y0) * scale)) for x, y, _ in face["landmarks"]]
    return crop, points


@st.cache_data(show_spinner=False)
def lighting_maps(path: str, faces: list) -> list:
    """Each face's lightness as a heat map, marked with where vision.lighting() measures.

    The line down the nose splits the face for contour (one side lit more than the other);
    circles are the cheek, under-eye, forehead and chin patches, labelled with their lightness.
    """
    rgb = vision.decode_image(Path(path).read_bytes())
    maps = []
    for face in faces:
        crop, points = face_crop(rgb, face)
        lightness = cv2.cvtColor(crop, cv2.COLOR_RGB2LAB)[:, :, 0]
        heat = cv2.cvtColor(cv2.applyColorMap(lightness, cv2.COLORMAP_INFERNO), cv2.COLOR_BGR2RGB)
        hull = np.zeros(lightness.shape, np.uint8)
        cv2.fillConvexPoly(hull, cv2.convexHull(np.array(points, np.int32)), 1)
        inside = hull.astype(bool)
        view = (crop * 0.35).astype(np.uint8)
        view[inside] = heat[inside]

        def label(text: str, at: tuple) -> None:
            cv2.putText(view, text, at, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(view, text, at, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

        # Contour: the face split down the nose, each half's average lightness.
        nose_x = points[vision.NOSE_TIP_POINT][0]
        columns = np.arange(view.shape[1])[None, :]
        top = min(y for _, y in points)
        bottom = max(y for _, y in points)
        cv2.line(view, (nose_x, top), (nose_x, bottom), (255, 255, 255), 2)
        for side, mask, x in (("left", columns < nose_x, 8), ("right", columns >= nose_x, nose_x + 8)):
            values = lightness[inside & mask]
            if values.size:
                label(f"{side} half {np.mean(values) / 255:.2f}", (x, bottom - 8))

        # The patches lighting() samples, with each one's average lightness.
        radius = max(2, int((bottom - top) * vision.LIGHT_PATCH))
        patches = [("cheek", i) for i in vision.CHEEK_POINTS] + [("under eye", i) for i in vision.UNDER_EYE_POINTS] \
            + [("forehead", vision.FOREHEAD_POINT), ("chin", vision.CHIN_POINT)]
        for name, i in patches:
            mask = np.zeros(lightness.shape, np.uint8)
            cv2.circle(mask, points[i], radius, 1, -1)
            cv2.circle(view, points[i], radius, (255, 255, 255), 2)
            label(f"{name} {np.mean(lightness[mask.astype(bool)]) / 255:.2f}",
                  (points[i][0] - radius, points[i][1] - radius - 6))
        maps.append(view)
    return maps


@st.cache_data(show_spinner=False)
def colour_views(path: str, faces: list) -> list:
    """For each face: the photo marked with where colour is sampled, a redness map, colour
    swatches per region, and a table of each region's brightness and colour.

    Redness is LAB's a channel, so blush and lip colour stand out; contour makeup shows up as
    the area under the cheekbone and the jawline being darker than the cheekbone.
    """
    rgb = vision.decode_image(Path(path).read_bytes())
    views = []
    for face in faces:
        crop, points = face_crop(rgb, face)
        lab = cv2.cvtColor(crop, cv2.COLOR_RGB2LAB)
        face_height = max(y for _, y in points) - min(y for _, y in points)
        hull = np.zeros(crop.shape[:2], np.uint8)
        cv2.fillConvexPoly(hull, cv2.convexHull(np.array(points, np.int32)), 1)

        marked, rows, swatches = crop.copy(), [], []
        for region, indices in vision.COLOUR_POINTS.items():
            radius = max(2, int(face_height * (vision.LIP_PATCH if region == "lips" else vision.LIGHT_PATCH)))
            mask = np.zeros(crop.shape[:2], np.uint8)
            for i in indices:
                cv2.circle(mask, points[i], radius, 1, -1)
                cv2.circle(marked, points[i], radius, (255, 255, 255), 2)
            inside = mask.astype(bool)
            colour = crop[inside].mean(axis=0)
            l, a, b = lab[inside].mean(axis=0)
            rows.append({"region": region.replace("_", " "), "brightness": round(float(l) / 255, 3),
                         "redness": round(float(a) / 128 - 1, 3), "yellowness": round(float(b) / 128 - 1, 3),
                         "colour": "#%02x%02x%02x" % tuple(int(c) for c in colour)})
            swatch = np.full((SWATCH_SIZE, SWATCH_SIZE * 2, 3), colour, np.uint8)
            cv2.putText(swatch, region.replace("_", " "), (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                        (0, 0, 0) if l > 140 else (255, 255, 255), 1, cv2.LINE_AA)
            swatches.append(swatch)

        # Redness map: LAB a channel, stretched so the face's own range fills the colour scale.
        a_channel = lab[:, :, 1].astype(np.float32)
        on_face = a_channel[hull.astype(bool)]
        low, high = np.percentile(on_face, 2), np.percentile(on_face, 98)
        stretched = np.clip((a_channel - low) / max(high - low, 1) * 255, 0, 255).astype(np.uint8)
        heat = cv2.cvtColor(cv2.applyColorMap(stretched, cv2.COLORMAP_MAGMA), cv2.COLOR_BGR2RGB)
        redness = (crop * 0.35).astype(np.uint8)
        redness[hull.astype(bool)] = heat[hull.astype(bool)]

        grid = [np.hstack(swatches[i:i + 2] + [np.full_like(swatches[0], 255)] * (2 - len(swatches[i:i + 2])))
                for i in range(0, len(swatches), 2)]
        views.append({"marked": marked, "redness": redness, "swatches": np.vstack(grid), "rows": rows})
    return views


@st.cache_data(show_spinner=False)
def face_closeups(path: str, faces: list) -> list:
    """A close-up of each face with all 478 face points drawn, outlines coloured by region."""
    rgb = vision.decode_image(Path(path).read_bytes())
    height, width = rgb.shape[:2]
    closeups = []
    for face in faces:
        crop, points = face_crop(rgb, face)
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
            show_table({**face.get("measurements", {}), "cut_off": face["cut_off"],
                        **({"hand_over_face": face["hand_over_face"]} if "hand_over_face" in face else {})})
            if face.get("lighting"):
                with st.expander("Lighting and contour", expanded=True):
                    st.image(lighting_maps(str(path), result["faces"])[i],
                             caption="Brightness on the face: yellow is bright, purple is dark. The line "
                                     "splits the face for contour; circles are where cheek, under-eye, "
                                     "forehead and chin light is measured (0 = black, 1 = white).")
                    show_table(face["lighting"])
                colour = colour_views(str(path), result["faces"])[i]
                with st.expander("Face colour and makeup", expanded=True):
                    marked, redness = st.columns(2)
                    marked.image(colour["marked"], caption="Where colour is sampled")
                    redness.image(colour["redness"], caption="Redness: bright is redder (blush, lips), "
                                                             "dark is less red")
                    st.image(colour["swatches"], caption="Average colour of each region")
                    if face.get("colour"):
                        st.markdown("What the model learns from (each compares two parts of your face):")
                        show_table({k: v for k, v in face["colour"].items() if k != "regions"})
                    st.dataframe(colour["rows"], hide_index=True)
            st.image(closeup, caption=f"All {len(face['landmarks'])} face points; outlines: "
                     + ", ".join(vision.LANDMARK_REGIONS))
            by_region = {}
            for name, score in face.get("expressions", {}).items():
                by_region.setdefault(ranker_region(name), {})[name] = score
            for region, scores in by_region.items():
                with st.expander(f"{region}: {len(scores)} expression scores"):
                    show_table(dict(sorted(scores.items(), key=lambda kv: -kv[1])))
