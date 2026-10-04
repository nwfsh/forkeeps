"""Everyone's "pick the better photo" choices, and the weights learned from them, in one SQLite database.

Replaces the per-person JSON files in preferences/; compare.py reads and writes here. Each
time someone's learned weights change, a new row is kept, so their history can be compared.
The app's keep/remove swipes on its own photos are kept here too (see save_verdict).

Run from server/:  python choices_db.py import    copy preferences/*.json in (safe to repeat)
"""
import json
import re
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

PREFERENCES = Path(__file__).resolve().parent / "preferences"
DB_PATH = PREFERENCES / "choices.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS choices (
    id           INTEGER PRIMARY KEY,
    person       TEXT NOT NULL,
    -- Photo paths from the repo root, e.g. data/training-recognition/sarah/IMG_4960.JPG.
    winner       TEXT NOT NULL,
    loser        TEXT NOT NULL,
    -- Whether the model gave the winner better odds before the pick; NULL before it had
    -- learned anything.
    model_agreed INTEGER,
    at           TEXT NOT NULL,
    UNIQUE (person, winner, loser, at)
);
CREATE INDEX IF NOT EXISTS choices_by_person ON choices (person, id);
CREATE TABLE IF NOT EXISTS weights (
    id         INTEGER PRIMARY KEY,
    person     TEXT NOT NULL,
    saved_at   TEXT NOT NULL,
    -- How many usable picks the weights were learned from, and how sure the ranker was.
    picks      INTEGER NOT NULL,
    confidence REAL,
    -- Everything Ranker.export() gives (weights, scaling, priorities, regions), as JSON.
    data       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS weights_by_person ON weights (person, id);
-- Picks between held-back test photos, made the same way as training picks. Only ever used to
-- check how well someone's learned weights match their taste, never to train them.
CREATE TABLE IF NOT EXISTS test_choices (
    id     INTEGER PRIMARY KEY,
    person TEXT NOT NULL,
    winner TEXT NOT NULL,
    loser  TEXT NOT NULL,
    at     TEXT NOT NULL
);
-- Keep or remove, swiped on one photo at a time in the app's photo review. The image itself
-- stays on the phone (or is deleted there); only its ranker features are kept here.
CREATE TABLE IF NOT EXISTS verdicts (
    id       INTEGER PRIMARY KEY,
    person   TEXT NOT NULL,
    -- The app's id for the photo, e.g. its capture time.
    photo    TEXT NOT NULL,
    verdict  TEXT NOT NULL CHECK (verdict IN ('keep', 'remove')),
    -- ranker.photo_features() as JSON; NULL when the app had no analysis for the photo.
    features TEXT,
    at       TEXT NOT NULL,
    UNIQUE (person, photo)
);
"""
VERDICTS = ("keep", "remove")


def person_key(name: str) -> str:
    """The name as stored, matching the old preferences/<name>.json file names."""
    return re.sub(r"[^A-Za-z0-9_-]", "", name) or "me"


def connect(path: Path = None) -> sqlite3.Connection:
    path = path or DB_PATH
    path.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def photo_path(path: str) -> str:
    """A photo path with forward slashes, so picks made on Windows and on a Mac match."""
    return path.replace("\\", "/")


def as_choice(row: sqlite3.Row) -> dict:
    agreed = row["model_agreed"]
    return {"winner": photo_path(row["winner"]), "loser": photo_path(row["loser"]),
            "model_agreed": None if agreed is None else bool(agreed), "at": row["at"]}


def load(name: str) -> list[dict]:
    """One person's choices, oldest first, shaped like the old JSON entries."""
    with closing(connect()) as conn:
        rows = conn.execute("SELECT * FROM choices WHERE person = ? ORDER BY id", (person_key(name),))
        return [as_choice(r) for r in rows]


def add(name: str, winner: str, loser: str, model_agreed: Optional[bool], at: str = None) -> None:
    at = at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    with closing(connect()) as conn, conn:
        conn.execute("INSERT OR IGNORE INTO choices (person, winner, loser, model_agreed, at) "
                     "VALUES (?, ?, ?, ?, ?)",
                     (person_key(name), photo_path(winner), photo_path(loser), model_agreed, at))


def remove_last(name: str) -> Optional[dict]:
    """Delete and return someone's most recent choice, or None if they have none."""
    with closing(connect()) as conn, conn:
        row = conn.execute("SELECT * FROM choices WHERE person = ? ORDER BY id DESC LIMIT 1",
                           (person_key(name),)).fetchone()
        if row:
            conn.execute("DELETE FROM choices WHERE id = ?", (row["id"],))
    return as_choice(row) if row else None


def clear(name: str) -> int:
    """Delete all of someone's choices. Returns how many there were."""
    with closing(connect()) as conn, conn:
        return conn.execute("DELETE FROM choices WHERE person = ?", (person_key(name),)).rowcount


def save_weights(name: str, picks: int, confidence: float, data: dict) -> bool:
    """Keep a new row of learned weights, unless they're the same as the person's latest.

    Opening the results again without new picks learns the same weights; skipping those keeps
    the history meaningful and the database file unchanged. Returns whether a row was added.
    """
    text = json.dumps(data, sort_keys=True)
    with closing(connect()) as conn, conn:
        latest = conn.execute("SELECT picks, data FROM weights WHERE person = ? ORDER BY id DESC LIMIT 1",
                              (person_key(name),)).fetchone()
        if latest and latest["picks"] == picks and latest["data"] == text:
            return False
        conn.execute("INSERT INTO weights (person, saved_at, picks, confidence, data) VALUES (?, ?, ?, ?, ?)",
                     (person_key(name), datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      picks, confidence, text))
        return True


def weights_history(name: str) -> list[dict]:
    """Every saved set of someone's weights, oldest first, with the data decoded."""
    with closing(connect()) as conn:
        rows = conn.execute("SELECT * FROM weights WHERE person = ? ORDER BY id", (person_key(name),))
        return [{"saved_at": r["saved_at"], "picks": r["picks"], "confidence": r["confidence"],
                 **json.loads(r["data"])} for r in rows]


def add_test_choice(name: str, winner: str, loser: str) -> None:
    """Record a pick between two test photos."""
    with closing(connect()) as conn, conn:
        conn.execute("INSERT INTO test_choices (person, winner, loser, at) VALUES (?, ?, ?, ?)",
                     (person_key(name), winner, loser, datetime.now(timezone.utc).isoformat(timespec="seconds")))


def load_test_choices(name: str) -> list[dict]:
    """Someone's picks between test photos, oldest first."""
    with closing(connect()) as conn:
        rows = conn.execute("SELECT * FROM test_choices WHERE person = ? ORDER BY id", (person_key(name),))
        return [{"winner": r["winner"], "loser": r["loser"], "at": r["at"]} for r in rows]


def clear_test_choices(name: str) -> int:
    """Delete all of someone's test picks. Returns how many there were."""
    with closing(connect()) as conn, conn:
        return conn.execute("DELETE FROM test_choices WHERE person = ?", (person_key(name),)).rowcount


def remove_last_test_choice(name: str) -> Optional[dict]:
    """Delete and return someone's most recent test pick, or None if they have none."""
    with closing(connect()) as conn, conn:
        row = conn.execute("SELECT * FROM test_choices WHERE person = ? ORDER BY id DESC LIMIT 1",
                           (person_key(name),)).fetchone()
        if row:
            conn.execute("DELETE FROM test_choices WHERE id = ?", (row["id"],))
    return {"winner": row["winner"], "loser": row["loser"], "at": row["at"]} if row else None


def save_verdict(name: str, photo: str, verdict: str, features: Optional[dict]) -> None:
    """Record keep or remove for one photo. Reviewing the same photo again replaces the old verdict."""
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {VERDICTS}")
    with closing(connect()) as conn, conn:
        conn.execute(
            "INSERT INTO verdicts (person, photo, verdict, features, at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (person, photo) DO UPDATE SET verdict = excluded.verdict, "
            "features = COALESCE(excluded.features, verdicts.features), at = excluded.at",
            (person_key(name), photo, verdict, None if features is None else json.dumps(features),
             datetime.now(timezone.utc).isoformat(timespec="seconds")))


def load_verdicts(name: str) -> list[dict]:
    """Someone's verdicts, oldest first, with features decoded (None if unknown)."""
    with closing(connect()) as conn:
        rows = conn.execute("SELECT * FROM verdicts WHERE person = ? ORDER BY id", (person_key(name),))
        return [{"photo": r["photo"], "verdict": r["verdict"], "at": r["at"],
                 "features": None if r["features"] is None else json.loads(r["features"])} for r in rows]


def verdict_pairs(name: str) -> tuple[dict, list[tuple[str, str]]]:
    """Verdicts as ranker input: features by photo, and a (kept, removed) pick for every pairing.

    Keeping one photo and removing another says the same as picking the first over the
    second, so these train a Ranker exactly like the "pick the better photo" choices.
    """
    verdicts = [v for v in load_verdicts(name) if v["features"] is not None]
    features = {f"app/{v['photo']}": v["features"] for v in verdicts}
    kept = [f"app/{v['photo']}" for v in verdicts if v["verdict"] == "keep"]
    removed = [f"app/{v['photo']}" for v in verdicts if v["verdict"] == "remove"]
    return features, [(k, r) for k in kept for r in removed]


def import_json(folder: Path = PREFERENCES) -> dict[str, int]:
    """Copy every <name>.json in the folder in, skipping choices already stored."""
    added = {}
    for path in sorted(folder.glob("*.json")):
        before = len(load(path.stem))
        for c in json.loads(path.read_text()):
            add(path.stem, c["winner"], c["loser"], c.get("model_agreed"), c["at"])
        added[path.stem] = len(load(path.stem)) - before
    return added


if __name__ == "__main__":
    if sys.argv[1:] != ["import"]:
        sys.exit(__doc__)
    for person, count in import_json().items():
        print(f"{person}: {count} new choices, {len(load(person))} in total")
