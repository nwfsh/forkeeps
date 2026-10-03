import time

from fastapi import FastAPI, File, HTTPException, UploadFile

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
