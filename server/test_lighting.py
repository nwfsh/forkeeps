"""Run from server/:  python -m pytest test_lighting.py"""
import numpy as np
import pytest

import vision
from ranker import photo_features

SIZE = 400
# The made-up face fills the middle fifth of the frame on each side.
FACE = (160, 240)


def made_up_landmarks() -> list:
    """478 points spread over a square face, with the sampled ones where a real face has them."""
    rng = np.random.default_rng(0)
    lo, hi = FACE[0] / SIZE, FACE[1] / SIZE
    points = [[x, y, 0.0] for x, y in rng.uniform(lo, hi, (478, 2))]
    for corner in ((lo, lo), (hi, lo), (lo, hi), (hi, hi)):  # so the outline is the whole square
        points.append([*corner, 0.0])
    mid = (lo + hi) / 2
    at = {vision.NOSE_TIP_POINT: (mid, mid), vision.FOREHEAD_POINT: (mid, lo + 0.02),
          vision.CHIN_POINT: (mid, hi - 0.02), vision.CHEEK_POINTS[0]: (lo + 0.02, mid + 0.02),
          vision.CHEEK_POINTS[1]: (hi - 0.02, mid + 0.02), vision.UNDER_EYE_POINTS[0]: (lo + 0.02, mid - 0.02),
          vision.UNDER_EYE_POINTS[1]: (hi - 0.02, mid - 0.02)}
    for i, (x, y) in at.items():
        points[i] = [x, y, 0.0]
    return points


def image(background: int, face: int, right_half=None) -> np.ndarray:
    """A grey frame with a grey face square; `right_half` gives the face's image-right side its own grey."""
    rgb = np.full((SIZE, SIZE, 3), background, np.uint8)
    a, b = FACE
    rgb[a:b, a:b] = face
    if right_half is not None:
        rgb[a:b, SIZE // 2:b] = right_half
    return rgb


def warning_codes(rgb: np.ndarray) -> list:
    face = {"bbox": {"x": 0.4, "y": 0.4, "w": 0.2, "h": 0.2}, "cut_off": False,
            "lighting": vision.lighting(rgb, made_up_landmarks())}
    return [w["code"] for w in vision.framing_warnings([face], [])]


def test_even_light_gives_no_lighting_warnings():
    light = vision.lighting(image(150, 180), made_up_landmarks())
    assert light["contour"] == pytest.approx(0, abs=0.01)
    # Not quite 0: the outline takes in a pixel's border of background.
    assert light["contrast"] < 0.03
    assert warning_codes(image(150, 180)) == []


def test_contour_says_which_side_is_lit():
    assert vision.lighting(image(150, 60, right_half=200), made_up_landmarks())["contour"] > 0.3
    assert vision.lighting(image(150, 200, right_half=60), made_up_landmarks())["contour"] < -0.3
    assert "side_shadow" in warning_codes(image(150, 60, right_half=200))


def test_dark_face_is_too_dark():
    assert vision.lighting(image(40, 40), made_up_landmarks())["brightness"] < vision.TOO_DARK
    assert warning_codes(image(40, 40)) == ["too_dark"]


def test_bright_background_behind_a_dark_face_is_backlit_not_just_dark():
    light = vision.lighting(image(250, 60), made_up_landmarks())
    assert light["backlight"] > vision.BACKLIT
    assert warning_codes(image(250, 60)) == ["backlit"]


def test_white_face_is_blown_out():
    assert vision.lighting(image(150, 255), made_up_landmarks())["blown_out"] > 0.95
    assert "blown_out" in warning_codes(image(150, 255))


def test_close_up_has_no_background_to_compare():
    # The same face stretched to fill nine-tenths of the frame.
    lo = FACE[0] / SIZE
    landmarks = [[(x - lo) * 4.5 + 0.05, (y - lo) * 4.5 + 0.05, z] for x, y, z in made_up_landmarks()]
    assert vision.lighting(image(150, 180), landmarks)["backlight"] is None


def test_ranker_reads_lighting_and_ignores_contour_direction():
    lighting = {"brightness": 0.7, "contrast": 0.2, "contour": -0.08, "under_eye_shadow": 0.1,
                "top_light": 0.15, "backlight": -0.05, "blown_out": 0.01, "warmth": 0.03}
    f = photo_features({"faces": [{"bbox": {"h": 0.3}, "cut_off": False, "lighting": lighting}], "people": []})
    assert f["bright_face"] == 0.7
    assert f["contour"] == pytest.approx(0.08)
    assert f["backlit"] == -0.05
    assert f["warm_light"] == 0.03


def test_results_without_lighting_still_work():
    f = photo_features({"faces": [{"bbox": {"h": 0.3}, "cut_off": False}], "people": []})
    assert f["bright_face"] is None and f["contour"] is None
