"""Run from server/:  python -m pytest test_personas.py"""
import makeup
import personas
import shots
import vision


def test_every_persona_has_every_line():
    for persona_id, persona in personas.PERSONAS.items():
        assert set(persona["lines"]) == set(personas.CLIPS), persona_id
        assert all(line.strip() for line in persona["lines"].values()), persona_id


# Clips spoken for taste instructions rather than warnings (see shots.INSTRUCTIONS).
TASTE_CLIPS = {clip for pair in shots.INSTRUCTIONS.values() for clip, _ in pair}
# Clips for makeup reminders (see makeup.CHECKS).
MAKEUP_CLIPS = {clip for _, _, clip, _ in makeup.CHECKS}
# Red flags with no framing warning of their own, which the app says by their code.
RED_FLAG_CLIPS = {"no_face", "face_too_small", "several_people"}


def test_every_warning_has_a_clip_the_personas_can_say():
    face = {"bbox": {"x": 0.3, "y": 0.2, "w": 0.3, "h": 0.3}, "cut_off": False}
    person = {"cut_at_joint": None}
    cases = [([], []), ([{**face, "covered_by": "hand"}], [])]
    cases += [([{**face, "cut_off": True, "bbox": bbox}], []) for bbox in (
        {"x": 0.0, "y": 0.3, "w": 0.3, "h": 0.3}, {"x": 0.7, "y": 0.3, "w": 0.3, "h": 0.3},
        {"x": 0.3, "y": 0.0, "w": 0.3, "h": 0.3}, {"x": 0.3, "y": 0.7, "w": 0.3, "h": 0.3})]
    cases += [([face], [{"cut_at_joint": joint}]) for joint in ("ankles", "knees", "hips")]
    cases += [([face], [{**person, "looking_room": 0.1, "facing": side}]) for side in ("left", "right")]
    cases += [([{**face, "bbox": {"x": 0.2, "y": 0.2, "w": 0.6, "h": 0.7}}], [person])]
    lit = {"brightness": 0.7, "backlight": 0.0, "blown_out": 0.0, "contour": 0.0, "under_eye_shadow": 0.1}
    cases += [([{**face, "lighting": {**lit, **change}}], []) for change in (
        {"backlight": 0.3}, {"brightness": 0.2}, {"blown_out": 0.2},
        {"contour": -0.3}, {"contour": 0.3}, {"under_eye_shadow": 0.4})]

    said = set()
    for faces, people in cases:
        warnings = vision.framing_warnings(faces, people)
        assert warnings
        said.update(w["clip"] for w in warnings)
    assert said == set(personas.CLIPS) - {"looks_good"} - TASTE_CLIPS - MAKEUP_CLIPS - RED_FLAG_CLIPS


def test_every_taste_instruction_has_a_clip():
    assert TASTE_CLIPS <= set(personas.CLIPS)


def test_recorded_lists_only_clips_that_exist(tmp_path, monkeypatch):
    monkeypatch.setattr(personas, "VOICES_FOLDER", tmp_path)
    assert personas.recorded("hype") == []
    path = personas.clip_path("hype", "too_close")
    path.parent.mkdir(parents=True)
    path.write_bytes(b"mp3")
    assert personas.recorded("hype") == ["too_close"]
    assert personas.recorded("strict") == []


def test_every_red_flag_has_a_clip():
    assert set(vision.RED_FLAGS) - {"face_cut_off"} <= set(personas.CLIPS)
