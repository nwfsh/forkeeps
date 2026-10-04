"""Run from server/:  python -m pytest test_personas.py"""
import personas
import vision


def test_every_persona_has_every_line():
    for persona_id, persona in personas.PERSONAS.items():
        assert set(persona["lines"]) == set(personas.CLIPS), persona_id
        assert all(line.strip() for line in persona["lines"].values()), persona_id


def test_every_warning_has_a_clip_the_personas_can_say():
    face = {"bbox": {"x": 0.3, "y": 0.2, "w": 0.3, "h": 0.3}, "cut_off": False}
    person = {"cut_at_joint": None}
    cases = [([], [])]
    cases += [([{**face, "cut_off": True, "bbox": bbox}], []) for bbox in (
        {"x": 0.0, "y": 0.3, "w": 0.3, "h": 0.3}, {"x": 0.7, "y": 0.3, "w": 0.3, "h": 0.3},
        {"x": 0.3, "y": 0.0, "w": 0.3, "h": 0.3}, {"x": 0.3, "y": 0.7, "w": 0.3, "h": 0.3})]
    cases += [([face], [{"cut_at_joint": joint}]) for joint in ("ankles", "knees", "hips")]
    cases += [([face], [{**person, "looking_room": 0.1, "facing": side}]) for side in ("left", "right")]
    cases += [([{**face, "bbox": {"x": 0.2, "y": 0.2, "w": 0.6, "h": 0.7}}], [person])]

    said = set()
    for faces, people in cases:
        warnings = vision.framing_warnings(faces, people)
        assert warnings
        said.update(w["clip"] for w in warnings)
    assert said == set(personas.CLIPS) - {"looks_good"}


def test_recorded_lists_only_clips_that_exist(tmp_path, monkeypatch):
    monkeypatch.setattr(personas, "VOICES_FOLDER", tmp_path)
    assert personas.recorded("hype") == []
    path = personas.clip_path("hype", "too_close")
    path.parent.mkdir(parents=True)
    path.write_bytes(b"mp3")
    assert personas.recorded("hype") == ["too_close"]
    assert personas.recorded("strict") == []
