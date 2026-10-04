"""Record every persona's lines with ElevenLabs.

Run from server/:  python generate_voices.py            (only lines that are new or changed)
                   python generate_voices.py hype       (just one persona)
                   python generate_voices.py --voices   (list the voices your account can use)

Needs ELEVENLABS_API_KEY in the environment or in server/.env.
"""
from __future__ import annotations

import hashlib
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

import certifi

from personas import CLIPS, MODEL, PERSONAS, VOICES_FOLDER, clip_path

API = "https://api.elevenlabs.io/v1"
# What each saved clip was made from, so a rerun only pays for lines that changed.
MANIFEST = VOICES_FOLDER / "manifest.json"
# python.org's Python on macOS ships without root certificates, so use certifi's.
CERTIFICATES = ssl.create_default_context(cafile=certifi.where())
ATTEMPTS = 3


def api_key() -> str:
    env_file = Path(__file__).resolve().parent / ".env"
    if "ELEVENLABS_API_KEY" not in os.environ and env_file.exists():
        for line in env_file.read_text().splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "ELEVENLABS_API_KEY":
                os.environ["ELEVENLABS_API_KEY"] = value.strip().strip("\"'")
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        sys.exit("Set ELEVENLABS_API_KEY in the environment or in server/.env")
    return key


def call(path: str, key: str, body: dict | None = None) -> bytes:
    request = urllib.request.Request(
        f"{API}{path}", headers={"xi-api-key": key, "Content-Type": "application/json"},
        data=None if body is None else json.dumps(body).encode())
    for attempt in range(ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=60, context=CERTIFICATES) as response:
                return response.read()
        except urllib.error.HTTPError as e:
            sys.exit(f"ElevenLabs returned {e.code} for {path}: {e.read().decode(errors='replace')[:500]}")
        except (urllib.error.URLError, TimeoutError) as e:
            # A slow or dropped connection is worth another go; anything ElevenLabs refuses isn't.
            if attempt == ATTEMPTS - 1:
                sys.exit(f"Couldn't reach ElevenLabs: {getattr(e, 'reason', e)}. Run again to carry on.")


def fingerprint(persona: dict, text: str) -> str:
    """Changes whenever the line, the voice or its settings change."""
    made_from = [text, persona["voice_id"], MODEL, persona["settings"]]
    return hashlib.sha1(json.dumps(made_from, sort_keys=True).encode()).hexdigest()


def list_voices(key: str) -> None:
    for voice in json.loads(call("/voices", key))["voices"]:
        labels = ", ".join(str(v) for v in (voice.get("labels") or {}).values())
        print(f"{voice['voice_id']}  {voice['name']}  ({labels})")


def generate(key: str, only: list[str]) -> None:
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    made = 0
    for persona_id, persona in PERSONAS.items():
        if only and persona_id not in only:
            continue
        for clip in CLIPS:
            text = persona["lines"][clip]
            path, mark = clip_path(persona_id, clip), fingerprint(persona, text)
            if path.exists() and manifest.get(f"{persona_id}/{clip}") == mark:
                continue
            print(f"{persona_id}/{clip}: {text}")
            audio = call(f"/text-to-speech/{persona['voice_id']}?output_format=mp3_44100_128", key,
                         {"text": text, "model_id": MODEL, "voice_settings": persona["settings"]})
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(audio)
            manifest[f"{persona_id}/{clip}"] = mark
            # Saved after every clip so a failure part-way doesn't redo the ones already paid for.
            MANIFEST.write_text(json.dumps(manifest, indent=1, sort_keys=True))
            made += 1
    print(f"Recorded {made} clip{'' if made == 1 else 's'}; the rest were already up to date.")


if __name__ == "__main__":
    args = sys.argv[1:]
    unknown = [a for a in args if a != "--voices" and a not in PERSONAS]
    if unknown:
        sys.exit(f"Unknown persona {', '.join(unknown)}. Choose from: {', '.join(PERSONAS)}")
    if "--voices" in args:
        list_voices(api_key())
    else:
        generate(api_key(), args)
