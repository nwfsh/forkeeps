import time

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

import personas
import vision

app = FastAPI()


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
    result["ms"] = round((time.perf_counter() - start) * 1000)
    return result


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
