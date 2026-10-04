"""Everyone's "pick the better photo" choices, in one SQLite database.

Replaces the per-person JSON files in preferences/; compare.py reads and writes here.

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
"""


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


def as_choice(row: sqlite3.Row) -> dict:
    agreed = row["model_agreed"]
    return {"winner": row["winner"], "loser": row["loser"],
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
                     "VALUES (?, ?, ?, ?, ?)", (person_key(name), winner, loser, model_agreed, at))


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
