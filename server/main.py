import time
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

import choices_db
import personas
import ranker
import recognize
import retrain
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
def analyze(image: UploadFile = File(...)):
    start = time.perf_counter()
    try:
        rgb = vision.decode_image(image.file.read())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    result = vision.analyze(rgb)
    add_names(rgb, result["faces"])
    result["ms"] = round((time.perf_counter() - start) * 1000)
    return result


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


@app.post("/verdicts")
def save_verdict(body: Verdict):
    """Keep or remove from the app's photo review. Only the photo's features are stored."""
    features = None
    if body.analysis is not None:
        try:
            features = ranker.photo_features(body.analysis)
        except (KeyError, TypeError) as e:
            raise HTTPException(status_code=400, detail=f"analysis isn't a /analyze result: {e}")
    try:
        choices_db.save_verdict(body.person, body.photo, body.verdict, features)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"saved": True, "measured": features is not None}


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


@app.get("/personas")
def list_personas():
    """The coach's voices, each with the clips that have been recorded for it."""
    return [{"id": persona_id, "name": persona["name"], "description": persona["description"],
             "clips": personas.recorded(persona_id)}
            for persona_id, persona in personas.PERSONAS.items()]


@app.get("/voice/{persona}/{clip}")
def voice(persona: str, clip: str):
    # Checked against the known names so the path can't be steered outside the voices folder.
    if persona not in personas.PERSONAS or clip not in personas.CLIPS:
        raise HTTPException(status_code=404, detail="No such voice clip")
    path = personas.clip_path(persona, clip)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Not recorded yet; run generate_voices.py")
    return FileResponse(path, media_type="audio/mpeg")
