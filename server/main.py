import math
import threading
import time
from typing import Literal, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

import angles
import choices_db
import comparing
import generate_voices
import makeup
import personas
import ranker
import recognize
import retrain
import shots
import snapshots
import subject
import vision

# Camera frames are small and faces in them are big, so the detector can work at a small
# size: on frames from a phone this matched the 640 default's names at about half the time.
LIVE_DETECT_SIZE = 320
# How much a recognised face's box must overlap a measured face's box to lend it its name.
SAME_FACE = 0.3

app = FastAPI()

# Names come from `python recognize.py enroll`. Without it, faces just have no name.
_references = recognize.load_references() if recognize.REFERENCES_PATH.exists() else {}
_recognizer = recognize.load_model(LIVE_DETECT_SIZE) if _references else None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze")
def analyze(image: UploadFile = File(...), person: Optional[str] = None):
    """Measure a frame. `shot` judges it as a photo, with `person`'s taste model if they have one."""
    start = time.perf_counter()
    try:
        rgb = vision.decode_image(image.file.read())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    result = vision.analyze(rgb)
    add_names(rgb, result["faces"])
    # With several people in the frame, judge only the person whose face it is (if it's been learned).
    result = subject.focus(result, rgb, person)
    result["shot"] = shots.judge(result, shots.load_model(person))
    # Makeup reminders against the person's reference look, if they've set one; not part of the score.
    result["makeup"] = makeup.check(result, makeup.load(person)) if person else []
    result["ms"] = round((time.perf_counter() - start) * 1000)
    return finite(result)


def finite(value):
    """The result with every NaN or infinite number made None, which JSON can't carry. A
    measurement over an empty patch (a face at the frame's edge, say) can come out NaN, and
    one unknown number shouldn't fail the whole frame."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: finite(v) for k, v in value.items()}
    if isinstance(value, list):
        return [finite(v) for v in value]
    return value


def add_names(rgb, faces: list[dict]) -> None:
    """Give each measured face the "name" of the known person whose face overlaps it, or None."""
    for face in faces:
        face["name"] = None
    if _recognizer is None or not faces:
        return
    known = recognize.find_faces(_recognizer, rgb)
    recognize.name_faces(known, _references)

    def box(b: dict) -> tuple:
        return (b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"])

    for person in (k for k in known if k["name"]):
        best = max(faces, key=lambda f: vision.overlap(box(f["bbox"]), box(person["bbox"])))
        if vision.overlap(box(best["bbox"]), box(person["bbox"])) >= SAME_FACE:
            best["name"] = person["name"]


class Verdict(BaseModel):
    person: str
    photo: str
    verdict: str
    # What /analyze said about the photo when it was taken, or None if it never got an answer.
    analysis: Optional[dict] = None
    # "angle" for a frame liked or passed over in the angle finder: only its head angle is kept.
    kind: Literal["photo", "angle"] = "photo"


class PickedPhoto(BaseModel):
    id: str
    # What /analyze said about the photo.
    analysis: dict


class Pick(BaseModel):
    person: str
    winner: PickedPhoto
    loser: PickedPhoto
    # True for "It's a tie": the two are equally good, and winner and loser are just the pair.
    tie: bool = False


@app.post("/picks")
def save_pick(body: Pick):
    """One "which do you like more?" choice, or a tie, from onboarding. Only measurements are stored."""
    try:
        winner, loser = ranker.photo_features(body.winner.analysis), ranker.photo_features(body.loser.analysis)
    except (KeyError, TypeError) as e:
        raise HTTPException(status_code=400, detail=f"analysis isn't a /analyze result: {e}")
    if body.tie:
        choices_db.save_measured_tie(body.person, body.winner.id, body.loser.id, winner, loser)
    else:
        choices_db.save_pick(body.person, body.winner.id, body.loser.id, winner, loser)
    return {"saved": True}


class CompareSession(BaseModel):
    # {"id", "analysis"} for each snapshot being compared.
    candidates: list[dict]
    # This session's picks so far: {"winner", "loser"} or {"a", "b", "tie": true}.
    picks: list[dict] = []
    # Pairs passed over with "Can't decide".
    skipped: list[list[str]] = []


@app.post("/pairs/next")
def next_pair(body: CompareSession):
    """The next pair to compare and whether to stop, decided like the Streamlit compare tool."""
    try:
        return comparing.next_step(body.candidates, body.picks, body.skipped)
    except (KeyError, TypeError) as e:
        raise HTTPException(status_code=400, detail=f"candidates need an id and a /analyze result: {e}")


@app.post("/verdicts")
def save_verdict(body: Verdict):
    """Keep or remove from the app's photo review or angle finder. Only features are stored."""
    features = None
    if body.analysis is not None:
        try:
            features = (angles.angle_features(body.analysis) if body.kind == "angle"
                        else ranker.photo_features(body.analysis))
        except (KeyError, TypeError) as e:
            raise HTTPException(status_code=400, detail=f"analysis isn't a /analyze result: {e}")
    try:
        choices_db.save_verdict(body.person, body.photo, body.verdict, features)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"saved": True, "measured": features is not None}


class SnapshotFrames(BaseModel):
    # {"id", "analysis"} for each frame of the onboarding recording.
    frames: list[dict]
    count: int = snapshots.SNAPSHOTS


@app.post("/snapshots")
def pick_snapshots(body: SnapshotFrames):
    """Pick about twenty varied, measurable frames from a recording for onboarding's swipes."""
    try:
        return snapshots.pick(body.frames, body.count)
    except (KeyError, TypeError) as e:
        raise HTTPException(status_code=400, detail=f"frames need an id and a /analyze result: {e}")


class AngleFrames(BaseModel):
    # {"id", "analysis"} for each frame the angle finder caught.
    frames: list[dict]


@app.post("/angles/cluster")
def cluster_angles(body: AngleFrames):
    """Group angle-finder frames by head angle and pick a typical frame from each group."""
    try:
        return angles.cluster(body.frames)
    except (KeyError, TypeError) as e:
        raise HTTPException(status_code=400, detail=f"frames need an id and a /analyze result: {e}")


@app.get("/model/{person}")
def model_status(person: str):
    """Reviewed-photo counts, and whether enough are new to offer retraining."""
    return retrain.status(person)


@app.post("/model/{person}/retrain")
def retrain_model(person: str):
    """Retrain this person's taste model from every photo they've kept or removed."""
    try:
        summary = retrain.retrain(person)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {**summary, "status": retrain.status(person)}


@app.post("/faces/{person}")
def learn_face(person: str, images: list[UploadFile] = File(...)):
    """Learn `person`'s face from photos of them (the app sends snapshots of the onboarding
    recording), so they can be told apart from other people in the frame."""
    try:
        used = subject.enroll(person, [vision.decode_image(image.file.read()) for image in images])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"person": person, "photos_used": used}


@app.post("/makeup/{person}")
def set_makeup_look(person: str, image: UploadFile = File(...)):
    """Keep a photo's lip and cheek colour as `person`'s makeup look; frames are checked against it."""
    try:
        result = vision.analyze(vision.decode_image(image.file.read()))
        return finite(makeup.save(person, makeup.reference_from(result)))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/makeup/{person}")
def get_makeup_look(person: str):
    look = makeup.load(person)
    if not look:
        raise HTTPException(status_code=404, detail="No makeup look set")
    return look


@app.delete("/makeup/{person}")
def clear_makeup_look(person: str):
    makeup.clear(person)
    return {"cleared": True}


@app.get("/personas")
def list_personas(person: Optional[str] = None):
    """The coach's voices, each with the clips that have been recorded for it. With `person`,
    also each voice calling them by name ("name_<person>"), recorded in the background the first
    time it's asked for."""
    name = personas.name_clip(person) if person else None
    if name and not all(personas.clip_path(p, name).exists() for p in personas.PERSONAS):
        record_name_later(person)
    return [{"id": persona_id, "name": persona["name"], "description": persona["description"],
             "clips": personas.recorded(persona_id)
             + ([name] if name and personas.clip_path(persona_id, name).exists() else [])}
            for persona_id, persona in personas.PERSONAS.items()]


_recording_names: set = set()


def record_name_later(person: str) -> None:
    """Records the voices saying this person's name, once, without holding up the request."""
    if person in _recording_names:
        return
    _recording_names.add(person)

    def record():
        try:
            generate_voices.record_name(generate_voices.api_key(), person)
        except (SystemExit, Exception) as e:  # call() exits on API errors; keep the server up
            print(f"Couldn't record {person}'s name: {e}")
        finally:
            _recording_names.discard(person)

    threading.Thread(target=record, daemon=True).start()


@app.get("/voice/{persona}/{clip}")
def voice(persona: str, clip: str):
    # Checked against the known names so the path can't be steered outside the voices folder.
    if persona not in personas.PERSONAS or (clip not in personas.CLIPS and not personas.is_name_clip(clip)):
        raise HTTPException(status_code=404, detail="No such voice clip")
    path = personas.clip_path(persona, clip)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Not recorded yet; run generate_voices.py")
    return FileResponse(path, media_type="audio/mpeg")
