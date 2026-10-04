"""Run from server/:  python -m pytest test_makeup.py"""
import pytest

import makeup

LOOK = {"lip_colour": 0.10, "blush": 0.04, "checks_blush": True}


def frame(lip_colour=0.10, blush=0.04, yaw=0.0, red_flags=()):
    face = {"colour": {"lip_colour": lip_colour, "blush": blush}, "pose": {"yaw": yaw}}
    return {"faces": [face], "red_flags": list(red_flags)}


def codes(result, look=LOOK):
    return [tip["code"] for tip in makeup.check(result, look)]


def test_nothing_to_say_when_the_look_is_still_on():
    assert codes(frame()) == []
    assert codes(frame(lip_colour=0.07, blush=0.03)) == []


def test_faded_lips_and_cheeks_are_reminded():
    assert codes(frame(lip_colour=0.04)) == ["lips_faded"]
    assert codes(frame(blush=0.005)) == ["blush_faded"]


def test_cheeks_are_only_mentioned_once_the_colour_is_all_but_gone():
    assert codes(frame(blush=0.02)) == []
    assert codes(frame(blush=0.012)) == []
    assert codes(frame(lip_colour=0.0, blush=-0.01)) == ["lips_faded", "blush_faded"]


def test_cheeks_without_blush_in_the_look_are_not_checked():
    assert codes(frame(blush=0.0), {**LOOK, "blush": 0.005, "checks_blush": False}) == []


def test_frames_that_cant_be_judged_say_nothing():
    assert codes(frame(lip_colour=0.0), None) == []
    assert codes(frame(lip_colour=0.0, yaw=45)) == []
    assert codes(frame(lip_colour=0.0, red_flags=["face_covered"])) == []
    assert codes({"faces": [], "red_flags": []}) == []


def test_reference_needs_one_readable_face():
    with pytest.raises(ValueError):
        makeup.reference_from({"faces": []})
    with pytest.raises(ValueError):
        makeup.reference_from({"faces": [{"colour": {}}]})


def test_reference_needs_a_clear_front_on_face():
    face = {"colour": {"lip_colour": 0.1, "blush": 0.04,
                       "regions": {k: {"hex": "#000000"} for k in ("lips", "cheek_apple", "forehead")}},
            "pose": {"yaw": 0.0}}
    assert makeup.reference_from({"faces": [face], "red_flags": []})["lip_colour"] == 0.1
    with pytest.raises(ValueError, match="in front of your face"):
        makeup.reference_from({"faces": [face], "red_flags": ["face_covered"]})
    with pytest.raises(ValueError, match="front-on"):
        makeup.reference_from({"faces": [{**face, "pose": {"yaw": 50.0}}], "red_flags": []})
