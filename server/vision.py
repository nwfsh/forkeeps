import math
import threading
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python import vision

MODEL_PATH = Path(__file__).parent / "models" / "face_landmarker.task"

# A face whose box comes within this fraction of the frame edge counts as cut off.
EDGE_MARGIN = 0.02
# Face height as a fraction of frame height, for a single-person shot.
TOO_FAR = 0.12
TOO_CLOSE = 0.55

_landmarker = vision.FaceLandmarker.create_from_options(
    vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(MODEL_PATH)),
        running_mode=vision.RunningMode.IMAGE,
        num_faces=8,
        output_facial_transformation_matrixes=True,
    )
)
# The landmarker isn't safe to call from several request threads at once.
_lock = threading.Lock()


def decode_image(data: bytes) -> np.ndarray:
    """Decode JPEG/PNG bytes to an RGB array, honouring EXIF orientation."""
    bgr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError("could not decode image")
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def head_pose(matrix) -> dict:
    """Yaw/pitch/roll in degrees from MediaPipe's 4x4 face transformation matrix."""
    r = np.asarray(matrix)[:3, :3]
    yaw = math.degrees(math.asin(max(-1.0, min(1.0, -r[2, 0]))))
    pitch = math.degrees(math.atan2(r[2, 1], r[2, 2]))
    roll = math.degrees(math.atan2(r[1, 0], r[0, 0]))
    return {"yaw": round(yaw, 1), "pitch": round(pitch, 1), "roll": round(roll, 1)}


def analyze(rgb: np.ndarray) -> dict:
    height, width = rgb.shape[:2]
    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
    with _lock:
        result = _landmarker.detect(image)

    faces = []
    for i, landmarks in enumerate(result.face_landmarks):
        xs = [p.x for p in landmarks]
        ys = [p.y for p in landmarks]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        face = {
            "bbox": {
                "x": round(x0, 4),
                "y": round(y0, 4),
                "w": round(x1 - x0, 4),
                "h": round(y1 - y0, 4),
            },
            "cut_off": x0 < EDGE_MARGIN or y0 < EDGE_MARGIN
            or x1 > 1 - EDGE_MARGIN or y1 > 1 - EDGE_MARGIN,
        }
        if i < len(result.facial_transformation_matrixes):
            face["pose"] = head_pose(result.facial_transformation_matrixes[i])
        faces.append(face)

    return {"width": width, "height": height, "faces": faces, "warnings": framing_warnings(faces)}


def framing_warnings(faces: list[dict]) -> list[dict]:
    """Basic framing checks, most important first. The personalised ranking replaces this later."""
    if not faces:
        return [{"code": "no_face", "message": "I can't see anyone"}]

    warnings = []
    cut = [f for f in faces if f["cut_off"]]
    if cut:
        side = edge_side(cut[0]["bbox"])
        who = "Someone is" if len(faces) > 1 else "You're"
        warnings.append({"code": "cut_off", "message": f"{who} cut off on the {side}"})

    if len(faces) == 1:
        h = faces[0]["bbox"]["h"]
        if h < TOO_FAR:
            warnings.append({"code": "too_far", "message": "Move closer"})
        elif h > TOO_CLOSE:
            warnings.append({"code": "too_close", "message": "Step back a little"})
    return warnings


def edge_side(bbox: dict) -> str:
    gaps = {
        "left": bbox["x"],
        "right": 1 - (bbox["x"] + bbox["w"]),
        "top": bbox["y"],
        "bottom": 1 - (bbox["y"] + bbox["h"]),
    }
    return min(gaps, key=gaps.get)
