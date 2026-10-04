import hashlib
import math
import threading
from pathlib import Path
from typing import Optional

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions
from mediapipe.python.solutions import face_mesh_connections as mesh
from mediapipe.tasks.python import vision

MODEL_PATH = Path(__file__).parent / "models" / "face_landmarker.task"
# The files whose code decides what a photo's results are.
ANALYSIS_CODE = ("vision.py", "ranker.py")
POSE_MODEL_PATH = Path(__file__).parent / "models" / "pose_landmarker_full.task"

# A face whose box comes within this fraction of the frame edge counts as cut off.
EDGE_MARGIN = 0.02
# Face height as a fraction of frame height, for a single-person shot.
TOO_CLOSE = 0.55
# Blendshape scores (0-1) above these decide the mode. Starting guesses; tune on real photos.
EYES_CLOSED = 0.6
SMILING = 0.5
GOOFY = 0.5
GOOFY_SHAPES = ("jawOpen", "mouthPucker", "cheekPuff", "tongueOut")
# Face crops are resized to this width before measuring sharpness, so photos of
# different resolutions and face sizes give comparable numbers.
SHARPNESS_WIDTH = 256
# When the whole image finds no face, retry on square crops this fraction of the
# image's shorter side, largest first.
ZOOM_STEPS = (0.5, 0.25)

# Photos are shrunk to this size on their longer side before pose detection.
POSE_SIZE = 1280
# Pose confidence cutoff for the second try when the default (0.5) finds nobody.
POSE_RETRY_CONFIDENCE = 0.1
# A nose at least this far inside the frame should have a findable face if it's facing us.
HIDDEN_FACE_MARGIN = 0.05
# Pose landmark indices (https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker).
NOSE, LEFT_EAR, RIGHT_EAR = 0, 7, 8
LEFT_SHOULDER, RIGHT_SHOULDER = 11, 12
LEFT_HIP, RIGHT_HIP = 23, 24
LEFT_KNEE, RIGHT_KNEE = 25, 26
LEFT_ANKLE, RIGHT_ANKLE = 27, 28
LEFT_ELBOW, RIGHT_ELBOW = 13, 14
LEFT_WRIST, RIGHT_WRIST = 15, 16
# Nose offset from the midpoint between the ears, in ear-gaps. Tuned on our own photos.
THREE_QUARTER_TURN = 0.4
PROFILE_TURN = 1.0
# Shoulder width over torso length, both in pixels. Square-on bodies are around 0.6-0.75.
SIDE_ON = 0.35
ANGLED = 0.5
# A frame edge within this fraction of the frame height of a joint "cuts at" that joint.
JOINT_MARGIN = 0.04
# Space in front of a turned head, as a fraction of frame width, below which it feels cramped.
LOOKING_ROOM = 0.3
# A face shorter than this fraction of the frame has too few pixels to read expressions from.
MIN_FACE_SIZE = 0.05
# Every expression score the face model gives (0-1 each), all kept.
EXPRESSIONS = [
    "_neutral", "browDownLeft", "browDownRight", "browInnerUp", "browOuterUpLeft", "browOuterUpRight",
    "cheekPuff", "cheekSquintLeft", "cheekSquintRight", "eyeBlinkLeft", "eyeBlinkRight",
    "eyeLookDownLeft", "eyeLookDownRight", "eyeLookInLeft", "eyeLookInRight", "eyeLookOutLeft",
    "eyeLookOutRight", "eyeLookUpLeft", "eyeLookUpRight", "eyeSquintLeft", "eyeSquintRight",
    "eyeWideLeft", "eyeWideRight", "jawForward", "jawLeft", "jawOpen", "jawRight", "mouthClose",
    "mouthDimpleLeft", "mouthDimpleRight", "mouthFrownLeft", "mouthFrownRight", "mouthFunnel",
    "mouthLeft", "mouthLowerDownLeft", "mouthLowerDownRight", "mouthPressLeft", "mouthPressRight",
    "mouthPucker", "mouthRight", "mouthRollLower", "mouthRollUpper", "mouthShrugLower",
    "mouthShrugUpper", "mouthSmileLeft", "mouthSmileRight", "mouthStretchLeft", "mouthStretchRight",
    "mouthUpperUpLeft", "mouthUpperUpRight", "noseSneerLeft", "noseSneerRight",
]
# Face region of each expression score, by its name's prefix.
EXPRESSION_REGIONS = {"brow": "Brows", "eye": "Eyes", "cheek": "Cheeks", "jaw": "Jaw",
                      "mouth": "Mouth", "nose": "Nose", "_neutral": "Overall"}
# Which of the 478 face points outline each region, as (point, point) edges to draw.
LANDMARK_REGIONS = {
    "Face oval": mesh.FACEMESH_FACE_OVAL,
    "Brows": mesh.FACEMESH_LEFT_EYEBROW | mesh.FACEMESH_RIGHT_EYEBROW,
    "Eyes": mesh.FACEMESH_LEFT_EYE | mesh.FACEMESH_RIGHT_EYE,
    "Irises": mesh.FACEMESH_IRISES,
    "Nose": mesh.FACEMESH_NOSE,
    "Mouth": mesh.FACEMESH_LIPS,
}
FACE_MESH = mesh.FACEMESH_TESSELATION
# Reasons a photo's measurements can't be trusted, so it shouldn't be used to learn preferences.
RED_FLAGS = {
    "no_person": "No one in the photo",
    "no_face": "Face not visible",
    "face_cut_off": "Face cut off by the frame",
    "face_too_small": "Face too small to measure",
    "several_people": "More than one person",
}

_landmarker = vision.FaceLandmarker.create_from_options(
    vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(MODEL_PATH)),
        running_mode=vision.RunningMode.IMAGE,
        num_faces=8,
        output_face_blendshapes=True,
        output_facial_transformation_matrixes=True,
    )
)
_pose_landmarker = vision.PoseLandmarker.create_from_options(
    vision.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(POSE_MODEL_PATH)),
        running_mode=vision.RunningMode.IMAGE,
        num_poses=4,
    )
)
# Retried only when the default finds nobody: long hair covering someone's whole back
# drops the model's confidence a lot, but a low cutoff on every photo is unreliable.
_pose_retry_landmarker = vision.PoseLandmarker.create_from_options(
    vision.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(POSE_MODEL_PATH)),
        running_mode=vision.RunningMode.IMAGE,
        num_poses=4,
        min_pose_detection_confidence=POSE_RETRY_CONFIDENCE,
        min_pose_presence_confidence=POSE_RETRY_CONFIDENCE,
    )
)
# The landmarker isn't safe to call from several request threads at once.
_lock = threading.Lock()


def code_version() -> str:
    """A fingerprint of the code that turns a photo into results, for keying caches.

    Streamlit only clears a cached function when that function's own code changes, so the
    apps pass this in to recompute photos after vision.py or ranker.py change.
    """
    here = Path(__file__).parent
    return hashlib.sha1(b"".join((here / name).read_bytes() for name in ANALYSIS_CODE)).hexdigest()


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


def detect(rgb: np.ndarray, top: int = 0, left: int = 0, side: Optional[int] = None) -> list[dict]:
    """Run the landmarker on the whole image, or on the square crop at (top, left).

    Face boxes come back as fractions of the whole image either way.
    """
    height, width = rgb.shape[:2]
    crop = rgb if side is None else rgb[top:top + side, left:left + side]
    crop_h, crop_w = crop.shape[:2]
    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(crop))
    with _lock:
        result = _landmarker.detect(image)

    found = []
    for i, landmarks in enumerate(result.face_landmarks):
        xs = [(left + p.x * crop_w) / width for p in landmarks]
        ys = [(top + p.y * crop_h) / height for p in landmarks]
        found.append({
            "box": (min(xs), min(ys), max(xs), max(ys)),
            # All 478 points, as fractions of the whole image; z is depth, on the x scale.
            "landmarks": [[round(x, 5), round(y, 5), round(p.z * crop_w / width, 5)]
                          for x, y, p in zip(xs, ys, landmarks)],
            "matrix": result.facial_transformation_matrixes[i]
            if i < len(result.facial_transformation_matrixes) else None,
            "blendshapes": result.face_blendshapes[i] if i < len(result.face_blendshapes) else None,
        })
    return found


def find_faces(rgb: np.ndarray) -> list[dict]:
    """Detect faces, zooming in with overlapping square crops when the whole image finds none.

    The detector shrinks its input to a small square, so a face that is a small part of a
    full-body shot gets lost. Crops make the face a bigger part of what the detector sees.
    """
    found = detect(rgb)
    if found:
        return found
    height, width = rgb.shape[:2]
    for fraction in ZOOM_STEPS:
        side = int(min(height, width) * fraction)
        stride = side // 2
        for top in crop_starts(height, side, stride):
            for left in crop_starts(width, side, stride):
                for face in detect(rgb, top, left, side):
                    # Neighbouring crops overlap, so the same face can be found twice.
                    if all(overlap(face["box"], other["box"]) < 0.3 for other in found):
                        found.append(face)
        if found:
            return found
    return found


def crop_starts(length: int, side: int, stride: int) -> list[int]:
    """Start positions for crops of `side` that step by `stride` and reach the far edge."""
    starts = list(range(0, max(0, length - side) + 1, stride))
    if starts[-1] + side < length:
        starts.append(length - side)
    return starts


def overlap(a: tuple, b: tuple) -> float:
    """Intersection over union of two (x0, y0, x1, y1) boxes."""
    w = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    h = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = w * h
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def find_people(rgb: np.ndarray) -> list[dict]:
    """Detect bodies and describe how each one is turned and framed."""
    height, width = rgb.shape[:2]
    scale = min(1.0, POSE_SIZE / max(height, width))
    small = cv2.resize(rgb, (round(width * scale), round(height * scale)))
    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(small))
    with _lock:
        result = _pose_landmarker.detect(image)
        if not result.pose_landmarks:
            result = _pose_retry_landmarker.detect(image)

    people, boxes = [], []
    for landmarks, world in zip(result.pose_landmarks, result.pose_world_landmarks):
        points = [(p.x, p.y) for p in landmarks]
        box = (min(x for x, _ in points), min(y for _, y in points),
               max(x for x, _ in points), max(y for _, y in points))
        # At a low cutoff the model can return the same person twice, slightly offset.
        if all(overlap(box, other) < 0.3 for other in boxes):
            boxes.append(box)
            person = describe_body(points, width, height)
            person.update(posture(np.array([[p.x, p.y, p.z] for p in world])))
            people.append(person)
    return people


def posture(world: np.ndarray) -> dict:
    """Slouch and arm measurements from the 33 pose points in metres (y points down).

    These use the model's 3D estimate, since slouching is a forward lean a flat image barely
    shows. That estimate isn't good enough to tell hands behind the back from hands in front,
    or crossed arms from hands on hips, so arm position is only measured, not named.
    """
    def unit(v: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(v)
        return v / norm if norm else v

    shoulders = (world[LEFT_SHOULDER] + world[RIGHT_SHOULDER]) / 2
    hips = (world[LEFT_HIP] + world[RIGHT_HIP]) / 2
    ears = (world[LEFT_EAR] + world[RIGHT_EAR]) / 2
    shoulder_width = np.linalg.norm(world[LEFT_SHOULDER] - world[RIGHT_SHOULDER]) or 1e-6
    up = unit(shoulders - hips)
    forward = unit(np.cross(world[LEFT_SHOULDER] - world[RIGHT_SHOULDER], up))
    if np.dot(world[NOSE] - ears, forward) < 0:
        forward = -forward
    head = ears - shoulders

    def elbow_gap(elbow: int, shoulder: int, hip: int) -> float:
        """Elbow's distance out from the line down that side of the body."""
        side = unit(world[hip] - world[shoulder])
        offset = world[elbow] - world[shoulder]
        return float(np.linalg.norm(offset - np.dot(offset, side) * side))

    return {
        # How far the head sits in front of the shoulders, relative to the spine. Slouching raises it.
        "head_forward": round(float(np.degrees(np.arctan2(np.dot(head, forward), np.dot(head, up)))), 1),
        # Ear height above the shoulders, in shoulder widths. Hunched shoulders shorten it.
        "neck_length": round(float(np.dot(head, up) / shoulder_width), 3),
        # Elbows' average distance from the body's sides, in shoulder widths.
        "arm_gap": round((elbow_gap(LEFT_ELBOW, LEFT_SHOULDER, LEFT_HIP)
                          + elbow_gap(RIGHT_ELBOW, RIGHT_SHOULDER, RIGHT_HIP)) / 2 / shoulder_width, 3),
        "hand_raised": bool(min(world[LEFT_WRIST][1], world[RIGHT_WRIST][1]) < shoulders[1]),
    }


def describe_body(points: list[tuple], width: int, height: int) -> dict:
    """View, body turn and framing from 33 pose points given as fractions of the frame.

    Points outside the frame are the model's guesses at where cut-off body parts are.
    """
    def mid(a: int, b: int) -> tuple:
        return ((points[a][0] + points[b][0]) / 2, (points[a][1] + points[b][1]) / 2)

    # Positive when the person's left shoulder is on the right of the image, i.e. facing us.
    shoulder_dx = (points[LEFT_SHOULDER][0] - points[RIGHT_SHOULDER][0]) * width
    shoulder_dy = (points[LEFT_SHOULDER][1] - points[RIGHT_SHOULDER][1]) * height
    torso = abs(mid(LEFT_HIP, RIGHT_HIP)[1] - mid(LEFT_SHOULDER, RIGHT_SHOULDER)[1]) * height
    width_ratio = abs(shoulder_dx) / torso if torso else 0.0

    ear_mid_x = mid(LEFT_EAR, RIGHT_EAR)[0]
    ear_gap = abs(points[LEFT_EAR][0] - points[RIGHT_EAR][0]) or 1e-6
    nose_x = points[NOSE][0]
    head_turn = (nose_x - ear_mid_x) / ear_gap

    # Unverified: we have no back-view photos yet. Reversed shoulders on a body that
    # isn't side-on should mean we're looking at someone's back.
    if shoulder_dx < 0 and width_ratio >= SIDE_ON:
        view = "back"
    elif abs(head_turn) >= PROFILE_TURN:
        view = "profile"
    elif abs(head_turn) >= THREE_QUARTER_TURN:
        view = "three_quarter"
    else:
        view = "front"

    body = {
        "view": view,
        "head_turn": round(head_turn, 2),
        "body_turn": "side_on" if width_ratio < SIDE_ON else "angled" if width_ratio < ANGLED else "square",
        "shoulder_width_ratio": round(width_ratio, 2),
        "shoulder_tilt": round(math.degrees(math.atan2(shoulder_dy, abs(shoulder_dx) or 1e-6)), 1),
        "crop": crop_name(points),
        "cut_at_joint": joint_at_edge(points),
        "body_size": round(min(1, max(y for _, y in points)) - max(0, min(y for _, y in points)), 3),
        "points": [[round(x, 4), round(y, 4)] for x, y in points],
    }
    if view in ("three_quarter", "profile"):
        # The direction the head points in the image, and how much frame is left that way.
        body["facing"] = "left" if head_turn < 0 else "right"
        body["looking_room"] = round(nose_x if head_turn < 0 else 1 - nose_x, 3)
    return body


def mark_back_if_face_hidden(person: dict) -> None:
    """Call a front or three-quarter body a back view when no face could be found.

    Hair over the shoulders hides the cues the pose model uses to tell front from back,
    so it often guesses front. A head well inside the frame that's really facing us
    would have given the face model something to find.
    """
    if person["view"] not in ("front", "three_quarter"):
        return
    nose_x, nose_y = person["points"][NOSE]
    inside = HIDDEN_FACE_MARGIN
    if inside <= nose_x <= 1 - inside and inside <= nose_y <= 1 - inside:
        person["view"] = "back"
        person.pop("facing", None)
        person.pop("looking_room", None)


def crop_name(points: list[tuple]) -> str:
    """How much of the body the frame shows, by the lowest body part inside it."""
    for name, (a, b) in (("full_body", (LEFT_ANKLE, RIGHT_ANKLE)),
                         ("knees_up", (LEFT_KNEE, RIGHT_KNEE)),
                         ("waist_up", (LEFT_HIP, RIGHT_HIP)),
                         ("shoulders_up", (LEFT_SHOULDER, RIGHT_SHOULDER))):
        if (points[a][1] + points[b][1]) / 2 <= 1:
            return name
    return "head_only"


def joint_at_edge(points: list[tuple]) -> Optional[str]:
    """The joint the bottom of the frame cuts across, if any. Cropping at a joint looks awkward.

    Only joints inside the frame count: the model's guesses for joints past the edge run
    low, so a frame cutting mid-thigh would otherwise read as cutting at the knees.
    """
    for name, (a, b) in (("ankles", (LEFT_ANKLE, RIGHT_ANKLE)),
                         ("knees", (LEFT_KNEE, RIGHT_KNEE)),
                         ("hips", (LEFT_HIP, RIGHT_HIP))):
        if 1 - JOINT_MARGIN < (points[a][1] + points[b][1]) / 2 <= 1:
            return name
    return None


def analyze(rgb: np.ndarray) -> dict:
    height, width = rgb.shape[:2]
    people = find_people(rgb)

    faces = []
    for found in find_faces(rgb):
        x0, y0, x1, y1 = found["box"]
        face = {
            "bbox": {
                "x": round(x0, 4),
                "y": round(y0, 4),
                "w": round(x1 - x0, 4),
                "h": round(y1 - y0, 4),
            },
            "cut_off": x0 < EDGE_MARGIN or y0 < EDGE_MARGIN
            or x1 > 1 - EDGE_MARGIN or y1 > 1 - EDGE_MARGIN,
            "landmarks": found["landmarks"],
        }
        if found["matrix"] is not None:
            face["pose"] = head_pose(found["matrix"])
        if found["blendshapes"] is not None:
            scores = {c.category_name: c.score for c in found["blendshapes"]}
            face["expressions"] = {name: round(score, 4) for name, score in scores.items()}
            face["measurements"] = measure(rgb, face, scores)
            face["mode"] = detect_mode(scores, face["measurements"])
            if len(people) == 1 and people[0]["view"] in ("profile", "back"):
                # Eye direction can't be read reliably when the head is turned this far.
                face["measurements"]["eyes_on_lens"] = None
        faces.append(face)

    if len(people) == 1 and not faces:
        mark_back_if_face_hidden(people[0])

    return {
        "width": width,
        "height": height,
        "faces": faces,
        "people": people,
        "warnings": framing_warnings(faces, people),
        "red_flags": red_flags(faces, people),
    }


def measure(rgb: np.ndarray, face: dict, scores: dict) -> dict:
    """The six per-frame measurements from the game plan."""
    blink = max(scores["eyeBlinkLeft"], scores["eyeBlinkRight"])
    look_away = max(
        scores[f"eyeLook{direction}{side}"]
        for direction in ("In", "Out", "Up", "Down")
        for side in ("Left", "Right")
    )
    pose = face.get("pose", {})
    return {
        "eye_openness": round(1 - blink, 3),
        "eyes_on_lens": round(1 - look_away, 3),
        "smile": round((scores["mouthSmileLeft"] + scores["mouthSmileRight"]) / 2, 3),
        "head_tilt": pose.get("roll"),
        "chin_angle": pose.get("pitch"),
        "face_size": face["bbox"]["h"],
        "sharpness": sharpness(rgb, face["bbox"]),
    }


def sharpness(rgb: np.ndarray, bbox: dict) -> float:
    """Variance of the Laplacian over the face; higher is sharper."""
    height, width = rgb.shape[:2]
    x0, y0 = max(0, int(bbox["x"] * width)), max(0, int(bbox["y"] * height))
    x1 = min(width, int((bbox["x"] + bbox["w"]) * width))
    y1 = min(height, int((bbox["y"] + bbox["h"]) * height))
    if x1 <= x0 or y1 <= y0:
        return 0.0
    gray = cv2.cvtColor(rgb[y0:y1, x0:x1], cv2.COLOR_RGB2GRAY)
    scale = SHARPNESS_WIDTH / gray.shape[1]
    gray = cv2.resize(gray, (SHARPNESS_WIDTH, max(1, round(gray.shape[0] * scale))))
    return round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 1)


def detect_mode(scores: dict, measurements: dict) -> str:
    """Smiling, serious, eyes closed or goofy, from a single frame."""
    if min(scores["eyeBlinkLeft"], scores["eyeBlinkRight"]) > EYES_CLOSED:
        return "eyes_closed"
    # Smiling is checked before goofy so an open-mouthed laugh counts as a smile.
    if measurements["smile"] > SMILING:
        return "smiling"
    if any(scores.get(name, 0) > GOOFY for name in GOOFY_SHAPES):
        return "goofy"
    return "serious"


def red_flags(faces: list[dict], people: list[dict]) -> list[str]:
    """Codes from RED_FLAGS for why this photo's measurements can't be trusted.

    These are about whether the photo can be measured, not whether it's a good photo:
    a blink or an awkward crop is a real preference and doesn't raise a flag.
    """
    if not faces and not people:
        return ["no_person"]
    flags = []
    if not faces:
        flags.append("no_face")
    if any(face["cut_off"] for face in faces):
        flags.append("face_cut_off")
    if faces and max(face["bbox"]["h"] for face in faces) < MIN_FACE_SIZE:
        flags.append("face_too_small")
    if len(faces) > 1 or len(people) > 1:
        flags.append("several_people")
    return flags


def framing_warnings(faces: list[dict], people: list[dict]) -> list[dict]:
    """Basic framing checks, most important first. The personalised ranking replaces this later.

    Each warning's clip names the line the coach's voices say for it (see personas.CLIPS).
    """
    if not faces and not people:
        return [{"code": "no_person", "clip": "no_person", "message": "I can't see anyone"}]

    warnings = []
    cut = [f for f in faces if f["cut_off"]]
    if cut:
        side = edge_side(cut[0]["bbox"])
        who = "Someone is" if len(faces) > 1 else "You're"
        warnings.append({"code": "cut_off", "clip": f"cut_off_{side}", "message": f"{who} cut off on the {side}"})

    if len(people) == 1:
        person = people[0]
        if person["cut_at_joint"]:
            warnings.append({"code": "cut_at_joint", "clip": f"cut_at_joint_{person['cut_at_joint']}",
                             "message": f"The frame cuts right at your {person['cut_at_joint']}"})
        if person.get("looking_room", 1) < LOOKING_ROOM:
            warnings.append({"code": "looking_room", "clip": f"looking_room_{person['facing']}",
                             "message": f"Leave more space on the {person['facing']}, where you're looking"})

    # No "move closer": waist-up and full-body shots are deliberate, so a small face isn't a mistake.
    if len(faces) == 1 and faces[0]["bbox"]["h"] > TOO_CLOSE:
        warnings.append({"code": "too_close", "clip": "too_close", "message": "Step back a little"})
    return warnings


def edge_side(bbox: dict) -> str:
    gaps = {
        "left": bbox["x"],
        "right": 1 - (bbox["x"] + bbox["w"]),
        "top": bbox["y"],
        "bottom": 1 - (bbox["y"] + bbox["h"]),
    }
    return min(gaps, key=gaps.get)
