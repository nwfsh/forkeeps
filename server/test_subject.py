"""Run from server/:  python -m pytest test_subject.py"""
import numpy as np

import subject


def face(x, name=None):
    return {"bbox": {"x": x, "y": 0.2, "w": 0.2, "h": 0.25}, "cut_off": False, "name": name}


def body(x):
    # Pose points spread over the face at x, so the head they make covers it.
    corners = [[x, 0.2], [x + 0.2, 0.2], [x, 0.45], [x + 0.2, 0.45]]
    return {"points": [corners[i % 4] for i in range(33)], "cut_at_joint": None, "view": "front"}


def result(faces, people):
    return {"faces": faces, "people": people, "warnings": [], "red_flags": ["several_people"]}


def test_one_person_is_left_alone(monkeypatch):
    monkeypatch.setattr(subject, "load", lambda person: np.ones(3))
    out = subject.focus(result([face(0.1)], [body(0.1)]), None, "avery")
    assert out["subject"] is None and len(out["faces"]) == 1


def test_the_learned_face_is_coached_and_others_are_fine(monkeypatch):
    monkeypatch.setattr(subject, "load", lambda person: np.ones(3))
    monkeypatch.setattr(subject, "find", lambda rgb, faces, ref: 1)
    out = subject.focus(result([face(0.1), face(0.6)], [body(0.1), body(0.6)]), None, "avery")
    assert out["subject"] == "found"
    assert out["faces"][0]["bbox"]["x"] == 0.6 and out["faces"][0]["name"] == "avery"
    assert "several_people" not in out["red_flags"]
    assert len(out["people"]) == 1 and len(out["others"]) == 1


def test_no_match_or_no_learned_face_keeps_the_flag(monkeypatch):
    crowd = result([face(0.1), face(0.6)], [body(0.1), body(0.6)])
    monkeypatch.setattr(subject, "load", lambda person: None)
    assert subject.focus(crowd, None, "avery")["subject"] == "not_enrolled"
    monkeypatch.setattr(subject, "load", lambda person: np.ones(3))
    monkeypatch.setattr(subject, "find", lambda rgb, faces, ref: None)
    out = subject.focus(crowd, None, "avery")
    assert out["subject"] == "unknown" and out["red_flags"] == ["several_people"]
