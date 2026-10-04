"""Run from server/:  python -m pytest test_obstruction.py"""
import vision

FACE = (0.4, 0.2, 0.6, 0.4)  # x0, y0, x1, y1


def hand_at(x: float, y: float, spread: float = 0.04) -> list[tuple]:
    """21 hand points scattered around (x, y)."""
    return [(x + spread * ((i % 5) - 2) / 2, y + spread * ((i // 5) - 2) / 2) for i in range(21)]


def blockers(hands=(), objects=()) -> dict:
    return {"hands": list(hands), "objects": list(objects)}


def test_hand_over_the_middle_of_the_face_covers_it():
    assert vision.covered_by(FACE, blockers(hands=[hand_at(0.5, 0.3)])) == "hand"


def test_peace_sign_beside_the_face_does_not():
    # Like our photos: fingertips reach the cheek, the rest of the hand is out to the side.
    assert vision.covered_by(FACE, blockers(hands=[hand_at(0.66, 0.32)])) is None


def test_hand_elsewhere_does_not():
    assert vision.covered_by(FACE, blockers(hands=[hand_at(0.5, 0.8)])) is None


def test_object_over_the_face_covers_it():
    phone = {"name": "cell phone", "box": (0.42, 0.22, 0.58, 0.38)}
    assert vision.covered_by(FACE, blockers(objects=[phone])) == "cell phone"


def test_object_overlapping_the_edge_does_not():
    phone = {"name": "cell phone", "box": (0.57, 0.3, 0.7, 0.5)}
    assert vision.covered_by(FACE, blockers(objects=[phone])) is None


def test_head_box_from_pose_points_contains_the_face_points():
    points = [(0.5 + 0.02 * (i % 3), 0.3 + 0.01 * i) for i in range(11)] + [(0.5, 0.9)] * 22
    x0, y0, x1, y1 = vision.head_box(points)
    assert all(x0 < x < x1 and y0 < y < y1 for x, y in points[:11])


def test_covered_face_warns_first_and_raises_a_red_flag():
    face = {"bbox": {"x": 0.4, "y": 0.2, "w": 0.2, "h": 0.2}, "cut_off": True, "covered_by": "hand"}
    warnings = vision.framing_warnings([face], [])
    assert warnings[0]["code"] == "face_covered"
    assert "face_covered" in vision.red_flags([face], [])


def test_face_hidden_entirely_counts_from_the_body():
    person = {"cut_at_joint": None, "face_covered_by": "hand"}
    assert vision.framing_warnings([], [person])[0]["code"] == "face_covered"
    assert "face_covered" in vision.red_flags([], [person])


def test_uncovered_face_has_no_warning():
    face = {"bbox": {"x": 0.4, "y": 0.2, "w": 0.2, "h": 0.2}, "cut_off": False, "covered_by": None}
    assert all(w["code"] != "face_covered" for w in vision.framing_warnings([face], []))
    assert "face_covered" not in vision.red_flags([face], [])
