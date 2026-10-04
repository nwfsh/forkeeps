import hashlib
import io
import math
import threading
from pathlib import Path
from typing import Optional

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener
from mediapipe.python.solutions import face_mesh_connections as mesh
from mediapipe.tasks.python import vision

register_heif_opener()

MODEL_PATH = Path(__file__).parent / "models" / "face_landmarker.task"
# The files whose code decides what a photo's results are.
ANALYSIS_CODE = ("vision.py", "ranker.py")
POSE_MODEL_PATH = Path(__file__).parent / "models" / "pose_landmarker_full.task"
HAND_MODEL_PATH = Path(__file__).parent / "models" / "hand_landmarker.task"
# The body model's hand points (wrist, pinky, index, thumb) for each hand. Only a backup for
# the hand model, which finds 21 points per hand but misses hands blurred by movement; these
# four only outline part of the hand, so they're spread out by HAND_SPREAD to cover more of it.
BODY_HAND_POINTS = ((15, 17, 19, 21), (16, 18, 20, 22))
HAND_SPREAD = 1.3
# Masks for hand-over-face overlap are drawn at this size on the longer side.
OVERLAP_SIZE = 400

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
# Something in front of the face is bad whatever anyone's taste, so it's checked by rule.
# The face model can't tell: it guesses the hidden features and carries on, so these look
# for the hand (with the hand model above) or object itself.
OBJECT_MODEL_PATH = Path(__file__).parent / "models" / "efficientdet_lite0.tflite"
# Hands and objects are looked for on a copy this size on its longer side.
BLOCKER_SIZE = 640
# Only the middle of a face box counts, trimmed by this fraction of its size on each side.
# The edges are cheeks, ears and hair, where a hand beside the face (a peace sign) belongs.
FACE_CORE_TRIM = 0.2
# Share of a hand's 21 points in the face's middle that counts as covering it. Hands beside
# the face in our photos put at most 10% of their points anywhere in the face box.
HAND_COVERS = 0.25
# Share of the face's middle an object's box must cover, and how sure the detector must be.
# A hand by the face misread as a phone covered at most 5% of the face box, at 0.42.
OBJECT_COVERS = 0.3
OBJECT_SURE = 0.5
# Pose points 0-10 are the nose, eyes, ears and mouth. With no face found, the head is their
# box grown by this fraction of its size on each side.
HEAD_POINTS = range(11)
HEAD_MARGIN = 0.3
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
# Face points that light is sampled around: mid-cheeks (image left, image right), just under
# each eye, the forehead and the chin. Checked by drawing them on our own photos.
CHEEK_POINTS = (205, 425)
UNDER_EYE_POINTS = (230, 450)
FOREHEAD_POINT, CHIN_POINT, NOSE_TIP_POINT = 151, 199, 4
# Light is averaged over a circle this fraction of the face height around each point.
LIGHT_PATCH = 0.06
# Face points whose surrounding colour is measured, per region. Checked by drawing them on our
# own photos: the cheekbone sits high on the outer cheek, under_cheekbone is where contour
# makeup goes, and the lip points are on the lips rather than the gap between them.
COLOUR_POINTS = {
    "forehead": (151,),
    "cheekbone": (117, 346),
    "cheek_apple": (50, 280),
    "under_cheekbone": (147, 376),
    "jawline": (136, 365),
    "under_eyes": (230, 450),
    "lips": (12, 15),
}
# Lips are thin, so they're sampled over a smaller circle than the rest of the face.
LIP_PATCH = 0.025
# Face points for face shape, as (image-left, image-right) pairs where paired. Checked by
# drawing them on our own photos.
FACE_TOP, CHIN_BOTTOM = 10, 152
CHEEKBONE_WIDTH = (234, 454)
JAW_WIDTH = (172, 397)
CHIN_WIDTH = (150, 379)
MIDLINE = (10, 168, 1, 152)
MIRRORED = ((33, 263), (133, 362), (70, 300), (98, 327), (61, 291), (234, 454), (172, 397), (150, 379))
# Eyelid points for eye opening: (top, bottom) pairs and (outer, inner) corners per eye.
EYE_LIDS = (((159, 145), (158, 153)), ((386, 374), (385, 380)))
EYE_CORNERS = ((33, 133), (263, 362))
# Inner lip outline, in order round the mouth (upper lip left to right, then lower lip back).
INNER_LIPS = (78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308, 324, 318, 402, 317, 14, 87, 178, 88, 95)
# Middle of the upper and lower inner lip, and how far apart they must be, as a share of the
# mouth's width, before the mouth counts as open enough to show teeth.
UPPER_INNER_LIP, LOWER_INNER_LIP = 13, 14
MIN_MOUTH_OPENING = 0.08
# Face shape is only measured this close to facing the camera; past it a turned head
# changes the widths and fakes asymmetry more than a correction can undo.
MAX_SHAPE_YAW = 30
# A pixel this much brighter than the face's median, and nearly colourless, is a shine spot.
SHINE_ABOVE_MEDIAN = 0.2
SHINE_MAX_CHROMA = 18
# The band below the chin searched for a fold, as a fraction of face length.
UNDER_CHIN_BAND = 0.12
# Backlight compares the face with everything outside a box this many face widths and heights
# around it; closer in, hair dominates and reads as a dark background.
BACKGROUND_CLEARANCE = 2.5
# Brightness (0-1, perceptual) above which a face pixel counts as blown out.
BLOWN_OUT = 0.96
# Lighting warnings. Starting guesses: our photos are all evenly lit (faces 0.64-0.79 bright,
# contour within ±0.1, under-eye shadow at most 0.19, blown out at most 1%, background never
# more than 0.02 brighter than the face), so these sit well past anything we've seen.
TOO_DARK = 0.45
BACKLIT = 0.15
TOO_MUCH_BLOWN_OUT = 0.05
HARSH_SIDE_SHADOW = 0.2
DARK_UNDER_EYES = 0.25
# Reasons a photo's measurements can't be trusted, so it shouldn't be used to learn preferences.
RED_FLAGS = {
    "no_person": "No one in the photo",
    "no_face": "Face not visible",
    "face_cut_off": "Face cut off by the frame",
    "face_too_small": "Face too small to measure",
    "several_people": "More than one person",
    "face_covered": "Something in front of the face",
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
_hand_landmarker = vision.HandLandmarker.create_from_options(
    vision.HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(HAND_MODEL_PATH)),
        running_mode=vision.RunningMode.IMAGE,
        num_hands=2,
    )
)
_object_detector = vision.ObjectDetector.create_from_options(
    vision.ObjectDetectorOptions(
        base_options=BaseOptions(model_asset_path=str(OBJECT_MODEL_PATH)),
        running_mode=vision.RunningMode.IMAGE,
        score_threshold=OBJECT_SURE,
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
    """Decode JPEG/PNG/HEIC bytes to an RGB array, honouring EXIF orientation.

    OpenCV can't read HEIC, the iPhone camera's default format, so that goes through Pillow.
    """
    bgr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if bgr is not None:
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    try:
        with Image.open(io.BytesIO(data)) as image:
            return np.array(ImageOps.exif_transpose(image).convert("RGB"))
    except (OSError, ValueError) as error:
        raise ValueError("could not decode image") from error


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


def hand_over_face(rgb: np.ndarray, face_landmarks: list, body_points: Optional[list]) -> float:
    """Share of the face that hands cover, from 0 (clear) to 1.

    Hands come from the hand model's 21 points each; the body model's rougher hand points are
    used too, and the larger overlap counts, so a hand blurred by movement isn't missed.
    """
    height, width = rgb.shape[:2]
    scale = min(1.0, POSE_SIZE / max(height, width))
    small = cv2.resize(rgb, (round(width * scale), round(height * scale)))
    with _lock:
        hands = _hand_landmarker.detect(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(small))).hand_landmarks

    m = OVERLAP_SIZE / max(height, width)
    face = np.zeros((int(height * m) + 1, int(width * m) + 1), np.uint8)
    cv2.fillConvexPoly(face, cv2.convexHull(
        np.array([[x * width * m, y * height * m] for x, y, _ in face_landmarks], np.int32)), 1)
    face_area = max(int(face.sum()), 1)

    def covered(outlines: list) -> float:
        mask = np.zeros_like(face)
        for outline in outlines:
            cv2.fillConvexPoly(mask, cv2.convexHull(np.array(outline, np.int32)), 1)
        return float((face & mask).sum() / face_area)

    from_hand_model = covered([[(p.x * width * m, p.y * height * m) for p in hand] for hand in hands])
    from_body = 0.0
    if body_points is not None:
        outlines = []
        for indices in BODY_HAND_POINTS:
            pts = np.array([[body_points[i][0] * width * m, body_points[i][1] * height * m] for i in indices])
            centre = pts.mean(axis=0)
            outlines.append(centre + (pts - centre) * HAND_SPREAD)
        from_body = covered(outlines)
    return round(max(from_hand_model, from_body), 3)


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


def find_blockers(rgb: np.ndarray) -> dict:
    """Hands (21 points each) and objects (name and box) that could be in front of a face.

    Everything is in fractions of the image; boxes are (x0, y0, x1, y1).
    """
    height, width = rgb.shape[:2]
    scale = min(1.0, BLOCKER_SIZE / max(height, width))
    small = cv2.resize(rgb, (round(width * scale), round(height * scale)))
    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(small))
    with _lock:
        hands = _hand_landmarker.detect(image)
        objects = _object_detector.detect(image)
    small_h, small_w = small.shape[:2]
    found = []
    for detection in objects.detections:
        name = detection.categories[0].category_name
        b = detection.bounding_box
        if name != "person":
            found.append({"name": name, "box": (b.origin_x / small_w, b.origin_y / small_h,
                                                (b.origin_x + b.width) / small_w,
                                                (b.origin_y + b.height) / small_h)})
    return {"hands": [[(p.x, p.y) for p in hand] for hand in hands.hand_landmarks], "objects": found}


def covered_by(box: tuple, blockers: dict) -> Optional[str]:
    """What's in front of the middle of a face box (x0, y0, x1, y1): "hand", an object's
    name, or None."""
    x0, y0, x1, y1 = box
    dx, dy = (x1 - x0) * FACE_CORE_TRIM, (y1 - y0) * FACE_CORE_TRIM
    core = (x0 + dx, y0 + dy, x1 - dx, y1 - dy)
    for hand in blockers["hands"]:
        inside = sum(core[0] <= x <= core[2] and core[1] <= y <= core[3] for x, y in hand)
        if inside / len(hand) >= HAND_COVERS:
            return "hand"
    core_area = (core[2] - core[0]) * (core[3] - core[1])
    for thing in blockers["objects"]:
        b = thing["box"]
        shared = (max(0.0, min(b[2], core[2]) - max(b[0], core[0]))
                  * max(0.0, min(b[3], core[3]) - max(b[1], core[1])))
        if core_area and shared / core_area >= OBJECT_COVERS:
            return thing["name"]
    return None


def head_box(points: list) -> tuple:
    """Where the head is from the pose points, for when the face model found no face."""
    xs = [points[i][0] for i in HEAD_POINTS]
    ys = [points[i][1] for i in HEAD_POINTS]
    dx, dy = (max(xs) - min(xs)) * HEAD_MARGIN, (max(ys) - min(ys)) * HEAD_MARGIN
    return (min(xs) - dx, min(ys) - dy, max(xs) + dx, max(ys) + dy)


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
    blockers = find_blockers(rgb)

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
            "lighting": lighting(rgb, found["landmarks"]),
            "colour": face_colour(rgb, found["landmarks"]),
            "covered_by": covered_by(found["box"], blockers),
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
        face["shape"] = face_shape(rgb, found["landmarks"], face.get("pose"))
        faces.append(face)

    if len(people) == 1 and not faces:
        # A face hidden behind a hand isn't a back view.
        hidden_by = covered_by(head_box(people[0]["points"]), blockers)
        if hidden_by:
            people[0]["face_covered_by"] = hidden_by
        else:
            mark_back_if_face_hidden(people[0])
    if faces:
        main = max(faces, key=lambda f: f["bbox"]["h"])
        main["hand_over_face"] = hand_over_face(rgb, main["landmarks"], people[0]["points"] if people else None)

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


def face_shape(rgb: np.ndarray, landmarks: list, pose: Optional[dict]) -> dict:
    """Face proportions, symmetry, eye opening, teeth and gums, under-chin fold and shine.

    These describe how the face looks in this photo (angle, expression and light all change
    them), not a fixed trait of the person, and are only ever compared with the same person's
    other photos. Ratios are left out (None) when the head is turned too far to measure them.
    """
    height, width = rgb.shape[:2]
    # Pixels, with depth on the same scale as x.
    pts = np.array([[x * width, y * height, z * width] for x, y, z in landmarks], dtype=np.float64)
    yaw = (pose or {}).get("yaw", 0.0)

    # Undo head tilt (roll) using the forehead-to-chin line, then head turn (yaw) using depth.
    top, chin = pts[FACE_TOP], pts[CHIN_BOTTOM]
    roll = math.atan2(chin[0] - top[0], chin[1] - top[1])
    c, s = math.cos(roll), math.sin(roll)
    x, y = pts[:, 0] - top[0], pts[:, 1] - top[1]
    straight = np.stack([x * c - y * s, x * s + y * c, pts[:, 2]], axis=1)
    t = math.radians(yaw)
    straight[:, 0] = straight[:, 0] * math.cos(t) + straight[:, 2] * math.sin(t)

    def span(pair: tuple) -> float:
        return float(abs(straight[pair[1], 0] - straight[pair[0], 0]))

    cheekbones = span(CHEEKBONE_WIDTH) or 1e-6
    length = float(np.linalg.norm(straight[CHIN_BOTTOM, :2] - straight[FACE_TOP, :2]))
    facing = abs(yaw) <= MAX_SHAPE_YAW

    shape = {}
    if facing:
        midline = float(np.mean(straight[list(MIDLINE), 0]))
        sideways = [abs((midline - straight[a, 0]) - (straight[b, 0] - midline)) for a, b in MIRRORED]
        upright = [abs(straight[a, 1] - straight[b, 1]) for a, b in MIRRORED]
        shape.update({
            # Lower means a narrower jaw for the cheekbones: a more V-shaped face.
            "jaw_to_cheekbones": round(span(JAW_WIDTH) / cheekbones, 3),
            # Lower means the chin narrows more from the jaw: a more tapered chin.
            "chin_to_jaw": round(span(CHIN_WIDTH) / (span(JAW_WIDTH) or 1e-6), 3),
            "face_length": round(length / cheekbones, 3),
            # How far mirrored points (eyes, brows, nose, mouth, jaw) are from matching, as a
            # share of face width. 0 is perfectly symmetrical.
            "asymmetry": round(float(np.mean(sideways) + np.mean(upright)) / cheekbones, 4),
        })

    # Eye opening: lid gap over eye width, per eye (left and right as seen in the image). A
    # turned head narrows the far eye in the photo, so like the proportions it needs to face us.
    if facing:
        openings = []
        for lids, (outer, inner) in zip(EYE_LIDS, EYE_CORNERS):
            gap = np.mean([np.linalg.norm(pts[a, :2] - pts[b, :2]) for a, b in lids])
            openings.append(gap / (np.linalg.norm(pts[outer, :2] - pts[inner, :2]) or 1e-6))
        shape["eye_opening"] = round(float(np.mean(openings)), 3)
        shape["uneven_eyes"] = round(float(abs(openings[0] - openings[1]) / (max(openings) or 1e-6)), 3)

    if facing:
        shape.update(teeth_and_gums(rgb, pts))
    shape.update(skin_detail(rgb, pts, length, facing))
    return shape


def teeth_and_gums(rgb: np.ndarray, pts: np.ndarray) -> dict:
    """How much of the mouth opening is teeth, and how much gum shows above the top teeth.

    Teeth are found as the brightest part of the mouth opening rather than by colour, since
    warm light makes them look pink. Gum is whatever sits between the upper lip and the top
    edge of the teeth, column by column across the middle of the mouth.
    """
    lips = pts[list(INNER_LIPS), :2].astype(np.int32)
    x0, y0 = lips.min(axis=0)
    x1, y1 = lips.max(axis=0)
    # Closed lips: the brightest bit of lip would otherwise pass for teeth.
    gap = np.linalg.norm(pts[UPPER_INNER_LIP, :2] - pts[LOWER_INNER_LIP, :2])
    if x1 - x0 < 4 or gap < (x1 - x0) * MIN_MOUTH_OPENING:
        return {"teeth_shown": 0.0, "gummy": 0.0}
    crop = rgb[y0:y1 + 1, x0:x1 + 1]
    mouth = np.zeros(crop.shape[:2], np.uint8)
    cv2.fillPoly(mouth, [lips - [x0, y0]], 1)
    mouth = mouth.astype(bool)
    if mouth.sum() < 30:
        return {"teeth_shown": 0.0, "gummy": 0.0}
    lab = cv2.cvtColor(crop, cv2.COLOR_RGB2LAB).astype(np.float32)
    lightness, redness = lab[:, :, 0] / 255, lab[:, :, 1] - 128
    teeth = mouth & (lightness > max(0.45, float(np.percentile(lightness[mouth], 60))))
    teeth_share = float(teeth.sum() / mouth.sum())
    if teeth_share < 0.05:
        return {"teeth_shown": round(teeth_share, 3), "gummy": 0.0}

    tooth_red = float(np.median(redness[teeth]))
    gum_heights, mouth_heights = [], []
    columns = range(int(crop.shape[1] * 0.2), int(crop.shape[1] * 0.8))
    for col in columns:
        inside = np.flatnonzero(mouth[:, col])
        found = np.flatnonzero(teeth[:, col])
        if inside.size == 0 or found.size == 0:
            continue
        lip, tooth_top = inside[0], found[0]
        band = slice(lip, tooth_top)
        # Gum is redder than the teeth and not the dark gap of the mouth.
        gum = (redness[band, col] > tooth_red + 6) & (lightness[band, col] > 0.25)
        gum_heights.append(gum.sum())
        mouth_heights.append(inside[-1] - inside[0] + 1)
    gummy = float(np.mean(gum_heights) / np.mean(mouth_heights)) if gum_heights else 0.0
    return {"teeth_shown": round(teeth_share, 3), "gummy": round(gummy, 3)}


def skin_detail(rgb: np.ndarray, pts: np.ndarray, face_length: float, facing: bool) -> dict:
    """Shine spots on the face, and how strong a fold shows just below the chin.

    The fold is only measured facing the camera: with the head turned, the jaw edge and hair
    make strong lines under the chin that aren't a fold.
    """
    height, width = rgb.shape[:2]
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    lightness = lab[:, :, 0] / 255
    chroma = np.hypot(lab[:, :, 1] - 128, lab[:, :, 2] - 128)
    face = np.zeros((height, width), np.uint8)
    cv2.fillConvexPoly(face, cv2.convexHull(pts[:, :2].astype(np.int32)), 1)
    face = face.astype(bool)
    if not face.any():
        return {}
    median = float(np.median(lightness[face]))
    shine = face & (lightness > median + SHINE_ABOVE_MEDIAN) & (chroma < SHINE_MAX_CHROMA)

    # Under-chin fold: horizontal light-dark edges in a band below the chin, compared with the
    # same kind of edges on the cheeks, so sharper or brighter photos don't read as folds.
    chin_x0, chin_x1 = sorted((int(pts[CHIN_WIDTH[0], 0]), int(pts[CHIN_WIDTH[1], 0])))
    chin_y = int(pts[CHIN_BOTTOM, 1])
    band_bottom = min(height, chin_y + max(3, int(face_length * UNDER_CHIN_BAND)))
    fold = None
    if facing and chin_x1 - chin_x0 > 4 and band_bottom - chin_y > 2:
        edges = np.abs(cv2.Sobel(lightness, cv2.CV_32F, 0, 1, ksize=3))
        under_chin = edges[chin_y:band_bottom, chin_x0:chin_x1]
        cheeks = edges[face & ~shine]
        fold = round(float(np.mean(under_chin) / (np.mean(cheeks) or 1e-6)), 3)
    return {"shine": round(float(shine.sum() / face.sum()), 4), "under_chin_fold": fold}


def face_colour(rgb: np.ndarray, landmarks: list) -> dict:
    """Average colour of each face region, and comparisons that show makeup and contour.

    Each comparison is between two parts of the same face in the same photo, so the light
    mostly cancels out: lip colour against the forehead, blush on the cheek apples against the
    forehead, and the cheekbone against the area under it and the jawline. Brightness is LAB
    lightness (0-1); redness and yellowness are LAB's a and b channels (0 is neutral).
    """
    height, width = rgb.shape[:2]
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    points = np.array([[x * width, y * height] for x, y, _ in landmarks], dtype=np.float32)
    face_height = points[:, 1].max() - points[:, 1].min()

    regions = {}
    for region, indices in COLOUR_POINTS.items():
        radius = max(2, int(face_height * (LIP_PATCH if region == "lips" else LIGHT_PATCH)))
        mask = np.zeros((height, width), np.uint8)
        for i in indices:
            cv2.circle(mask, (int(points[i][0]), int(points[i][1])), radius, 1, -1)
        inside = mask.astype(bool)
        if not inside.any():
            return {}
        l, a, b = lab[inside].mean(axis=0)
        r, g, bl = rgb[inside].mean(axis=0)
        regions[region] = {"brightness": round(float(l) / 255, 3), "redness": round(float(a) / 128 - 1, 3),
                           "yellowness": round(float(b) / 128 - 1, 3),
                           "hex": "#%02x%02x%02x" % (int(r), int(g), int(bl))}

    skin = regions["forehead"]
    return {
        "regions": regions,
        # How much redder the lips are than plain skin: bare lips are a little redder, lipstick a lot.
        "lip_colour": round(regions["lips"]["redness"] - skin["redness"], 3),
        # How much redder the cheek apples are than the forehead.
        "blush": round(regions["cheek_apple"]["redness"] - skin["redness"], 3),
        # How much brighter the cheekbone is than the hollow under it and than the jawline.
        "contour_depth": round(regions["cheekbone"]["brightness"] - regions["under_cheekbone"]["brightness"], 3),
        "jaw_definition": round(regions["cheekbone"]["brightness"] - regions["jawline"]["brightness"], 3),
        # Cheekbone against the forehead: highlighter or a sheen catching the light raises it.
        "cheekbone_highlight": round(regions["cheekbone"]["brightness"] - skin["brightness"], 3),
    }


def lighting(rgb: np.ndarray, landmarks: list) -> dict:
    """How the light falls on a face: brightness, contour (one side darker than the other),
    shadows under the eyes, light from above, backlight, blown-out skin and warmth.

    Brightness values are perceptual lightness from 0 (black) to 1 (white), so differences
    read the same in dark and bright photos.
    """
    height, width = rgb.shape[:2]
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    lightness = lab[:, :, 0].astype(np.float32) / 255
    points = np.array([[x * width, y * height] for x, y, _ in landmarks], dtype=np.float32)

    face = np.zeros((height, width), np.uint8)
    cv2.fillConvexPoly(face, cv2.convexHull(points).astype(np.int32), 1)
    face = face.astype(bool)
    if not face.any():
        return {}
    face_light = lightness[face]

    # Split the face down the nose: positive contour means the image-right side is lit.
    columns = np.arange(width)[None, :]
    nose_x = points[NOSE_TIP_POINT][0]
    left = lightness[face & (columns < nose_x)]
    right = lightness[face & (columns >= nose_x)]
    contour = float(np.mean(right) - np.mean(left)) if left.size and right.size else 0.0

    x0, y0 = points.min(axis=0)
    x1, y1 = points.max(axis=0)
    radius = max(2, int((y1 - y0) * LIGHT_PATCH))

    def patch(*indices: int) -> float:
        """Mean lightness in small circles around the given face points."""
        mask = np.zeros((height, width), np.uint8)
        for i in indices:
            cv2.circle(mask, (int(points[i][0]), int(points[i][1])), radius, 1, -1)
        return float(np.mean(lightness[mask.astype(bool)]))

    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    half_w, half_h = (x1 - x0) * BACKGROUND_CLEARANCE / 2, (y1 - y0) * BACKGROUND_CLEARANCE / 2
    surroundings = np.ones((height, width), bool)
    surroundings[max(0, int(cy - half_h)):min(height, int(cy + half_h)),
                 max(0, int(cx - half_w)):min(width, int(cx + half_w))] = False
    # A close-up leaves no background to compare with.
    background = float(np.median(lightness[surroundings])) if surroundings.mean() > 0.1 else None
    brightness = float(np.median(face_light))

    return {
        "brightness": round(brightness, 3),
        # Spread of light across the face; flat light is low, dramatic light is high.
        "contrast": round(float(np.std(face_light)), 3),
        "contour": round(contour, 3),
        "under_eye_shadow": round(patch(*CHEEK_POINTS) - patch(*UNDER_EYE_POINTS), 3),
        "top_light": round(patch(FOREHEAD_POINT) - patch(CHIN_POINT), 3),
        "backlight": None if background is None else round(background - brightness, 3),
        "blown_out": round(float(np.mean(face_light > BLOWN_OUT)), 3),
        # LAB's b channel: above 0 is yellow/warm light, below is blue/cool.
        "warmth": round(float(np.mean(lab[:, :, 2][face])) / 128 - 1, 3),
    }


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
    if face_covered(faces, people):
        flags.append("face_covered")
    return flags


def face_covered(faces: list[dict], people: list[dict]) -> bool:
    return any(f.get("covered_by") for f in faces) or any(p.get("face_covered_by") for p in people)


def framing_warnings(faces: list[dict], people: list[dict]) -> list[dict]:
    """Basic framing checks, most important first. The personalised ranking replaces this later.

    Each warning's clip names the line the coach's voices say for it (see personas.CLIPS).
    """
    if not faces and not people:
        return [{"code": "no_person", "clip": "no_person", "message": "I can't see anyone"}]

    warnings = []
    # Wrong whatever anyone's taste, so it comes first.
    if face_covered(faces, people):
        warnings.append({"code": "face_covered", "clip": "face_covered",
                         "message": "Something's in front of your face: move it out of the way"})
    cut = [f for f in faces if f["cut_off"]]
    if cut:
        side = edge_side(cut[0]["bbox"])
        who = "Someone is" if len(faces) > 1 else "You're"
        warnings.append({"code": "cut_off", "clip": f"cut_off_{side}", "message": f"{who} cut off on the {side}"})

    light = max(faces, key=lambda f: f["bbox"]["h"]).get("lighting", {}) if faces else {}
    if (light.get("backlight") or 0) > BACKLIT:
        warnings.append({"code": "backlit", "clip": "backlit", "message": "The light is behind you: turn to face it"})
    elif light.get("brightness", 1) < TOO_DARK:
        warnings.append({"code": "too_dark", "clip": "too_dark",
                         "message": "Your face is too dark: turn toward the light"})
    if light.get("blown_out", 0) > TOO_MUCH_BLOWN_OUT:
        warnings.append({"code": "blown_out", "clip": "blown_out",
                         "message": "Too much direct light on your face: find some shade"})

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

    # Softer lighting advice comes last: a shadowed side can be a deliberate contour.
    if abs(light.get("contour", 0)) > HARSH_SIDE_SHADOW:
        lit = "right" if light["contour"] > 0 else "left"
        warnings.append({"code": "side_shadow", "clip": f"side_shadow_{lit}",
                         "message": f"Half your face is in shadow: turn a little toward the light on the {lit}"})
    if light.get("under_eye_shadow", 0) > DARK_UNDER_EYES:
        warnings.append({"code": "under_eye_shadow", "clip": "under_eye_shadow",
                         "message": "Overhead light is shadowing your eyes: lift your chin or face a window"})
    return warnings


def edge_side(bbox: dict) -> str:
    gaps = {
        "left": bbox["x"],
        "right": 1 - (bbox["x"] + bbox["w"]),
        "top": bbox["y"],
        "bottom": 1 - (bbox["y"] + bbox["h"]),
    }
    return min(gaps, key=gaps.get)
