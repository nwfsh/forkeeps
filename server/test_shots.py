"""Run from server/:  python -m pytest test_shots.py"""
import json

import pytest

import shots


def result(eyes=0.95, warnings=(), red_flags=(), faces=1, sharpness=600.0, contact=0.9):
    face = {"bbox": {"x": 0.3, "y": 0.2, "w": 0.3, "h": 0.3}, "cut_off": False, "mode": "smiling",
            "measurements": {"eye_openness": eyes, "eyes_on_lens": contact, "smile": 0.6, "head_tilt": 0.0,
                             "chin_angle": 0.0, "face_size": 0.3, "sharpness": sharpness}}
    return {"faces": [face] * faces, "people": [], "red_flags": list(red_flags),
            "warnings": [{"code": code, "clip": code, "message": code} for code in warnings]}


@pytest.fixture(autouse=True)
def scratch_models(tmp_path, monkeypatch):
    monkeypatch.setattr(shots, "WEIGHTS_FOLDER", tmp_path)
    shots._models.clear()


def save_model(tmp_path, smile_weight: float):
    model = {"weights": {"smile": smile_weight}, "mean": {"smile": 0.5}, "std": {"smile": 0.1}}
    (tmp_path / "me.json").write_text(json.dumps(model))


def test_clean_frame_is_perfect_without_a_model():
    shot = shots.judge(result(), None)
    assert shot["perfect"] and shot["scored_by"] == "rules" and shot["blockers"] == []


def test_tips_blinks_and_red_flags_block_a_perfect_shot():
    assert shots.judge(result(warnings=["too_close"]), None)["blockers"] == ["too_close"]
    assert shots.judge(result(eyes=0.2), None)["blockers"] == ["eyes_closed"]
    assert "several_people" in shots.judge(result(red_flags=["several_people"], faces=2), None)["blockers"]


def test_rules_score_drops_with_each_tip():
    assert shots.judge(result(warnings=["a", "b"]), None)["score"] < shots.judge(result(), None)["score"]


def test_model_scores_and_can_veto(tmp_path):
    save_model(tmp_path, 2.0)  # likes smiling; the frame smiles more than average
    shot = shots.judge(result(), shots.load_model("me"))
    assert shot["scored_by"] == "model" and shot["score"] > 0.6 and shot["perfect"]
    save_model(tmp_path, -2.0)  # dislikes smiling
    shot = shots.judge(result(), shots.load_model("me"))
    assert shot["blockers"] == ["low_score"] and not shot["perfect"]


def test_no_model_for_unknown_people():
    assert shots.load_model("nobody") is None
    assert shots.load_model(None) is None


def test_rules_need_a_decent_score_too():
    shot = shots.judge(result(eyes=0.75, sharpness=5.0, contact=0.3), None)  # blurry, looking away
    assert shot["score"] < shots.RULES_PERFECT_SCORE and shot["blockers"] == ["low_score"]
