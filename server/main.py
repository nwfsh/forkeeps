import time

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

import personas
import recognize
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
