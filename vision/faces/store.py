"""SQLite identity vault. Raw frames and crops are never stored here."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from vision.faces.base import normalize_embedding


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FaceStore:
    """Local SQLite records for people, vectors, unknown clusters and sightings."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else Path(__file__).resolve().parents[2] / "memory" / "face_identity.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._lock, self._connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS persons (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    aliases TEXT NOT NULL DEFAULT '[]', consent INTEGER NOT NULL DEFAULT 1,
                    profile_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS exemplars (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    person_id TEXT NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
                    emb BLOB NOT NULL, dim INTEGER NOT NULL, backend TEXT NOT NULL,
                    quality REAL NOT NULL, source TEXT NOT NULL, anchor INTEGER NOT NULL DEFAULT 1,
                    negative INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS exemplar_person ON exemplars(person_id, backend, dim);
                CREATE TABLE IF NOT EXISTS unknowns (
                    id TEXT PRIMARY KEY, centroid BLOB NOT NULL, dim INTEGER NOT NULL,
                    backend TEXT NOT NULL, n INTEGER NOT NULL DEFAULT 1,
                    first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, snapshot_path TEXT
                );
                CREATE TABLE IF NOT EXISTS sightings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    person_id TEXT REFERENCES persons(id) ON DELETE CASCADE,
                    unknown_id TEXT REFERENCES unknowns(id) ON DELETE SET NULL,
                    label TEXT NOT NULL, camera TEXT NOT NULL, track_id TEXT NOT NULL,
                    similarity REAL, ts TEXT NOT NULL, snapshot_path TEXT
                );
                CREATE INDEX IF NOT EXISTS sightings_person_ts ON sightings(person_id, ts);
                CREATE INDEX IF NOT EXISTS sightings_unknown ON sightings(unknown_id);
                CREATE TABLE IF NOT EXISTS identity_corrections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, track_id TEXT NOT NULL,
                    claimed_label TEXT NOT NULL, correct_label TEXT NOT NULL,
                    ts TEXT NOT NULL, applied_action TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY, value TEXT NOT NULL
                );
            """)

    @staticmethod
    def _blob(embedding, dim: int | None = None) -> tuple[bytes, int]:
        vector = normalize_embedding(embedding, expected_dim=dim)
        return vector.astype("<f4", copy=False).tobytes(), int(vector.size)

    @staticmethod
    def _vector(blob, dim: int) -> np.ndarray:
        result = np.frombuffer(blob, dtype="<f4", count=int(dim)).copy()
        return normalize_embedding(result, expected_dim=int(dim))

    def create_person(self, name: str, *, consent: bool = True,
                      profile: dict | None = None, person_id: str | None = None) -> dict:
        clean = " ".join(str(name or "").split())
        if not clean or len(clean) > 80:
            raise ValueError("person name must contain 1–80 characters")
        now = _now()
        identifier = person_id or uuid.uuid4().hex
        with self._lock, self._connect() as db:
            existing = db.execute("SELECT * FROM persons WHERE name=? COLLATE NOCASE", (clean,)).fetchone()
            if existing:
                if profile:
                    merged = json.loads(existing["profile_json"] or "{}")
                    merged.update(profile)
                    db.execute("UPDATE persons SET profile_json=?, consent=?, updated_at=? WHERE id=?",
                               (json.dumps(merged, ensure_ascii=False), int(consent), now, existing["id"]))
                return self.get_person(existing["id"], db=db)
            db.execute("INSERT INTO persons(id,name,consent,profile_json,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                       (identifier, clean, int(consent), json.dumps(profile or {}, ensure_ascii=False), now, now))
        return self.get_person(identifier)

    def get_person(self, person_id: str, *, db=None) -> dict | None:
        if db is None:
            with self._connect() as connection:
                return self.get_person(person_id, db=connection)
        row = db.execute("SELECT * FROM persons WHERE id=?", (person_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["aliases"] = json.loads(result["aliases"] or "[]")
        result["profile"] = json.loads(result.pop("profile_json") or "{}")
        result["consent"] = bool(result["consent"])
        result["sample_count"] = db.execute(
            "SELECT count(*) FROM exemplars WHERE person_id=? AND negative=0", (person_id,)).fetchone()[0]
        return result

    def find_person(self, name: str) -> dict | None:
        clean = " ".join(str(name or "").split())
        with self._lock, self._connect() as db:
            row = db.execute("SELECT id FROM persons WHERE name=? COLLATE NOCASE", (clean,)).fetchone()
            return self.get_person(row["id"], db=db) if row else None

    def list_people(self) -> list[dict]:
        with self._lock, self._connect() as db:
            rows = db.execute("SELECT id FROM persons ORDER BY name COLLATE NOCASE").fetchall()
            return [self.get_person(row["id"], db=db) for row in rows]

    def add_exemplar(self, person_id: str, embedding, *, backend: str,
                     quality: float, source: str = "photo", anchor: bool = True,
                     negative: bool = False) -> int:
        quality = float(quality)
        if not 0 <= quality <= 1:
            raise ValueError("quality must be between 0 and 1")
        vector, dim = self._blob(embedding)
        with self._lock, self._connect() as db:
            if db.execute("SELECT 1 FROM persons WHERE id=?", (person_id,)).fetchone() is None:
                raise KeyError("unknown person")
            row = db.execute("SELECT backend,dim FROM exemplars WHERE person_id=? LIMIT 1", (person_id,)).fetchone()
            if row and (row["backend"] != backend or row["dim"] != dim):
                raise ValueError("backend/dimension changed; start a re-enrollment campaign")
            cursor = db.execute("INSERT INTO exemplars(person_id,emb,dim,backend,quality,source,anchor,negative,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                                (person_id, vector, dim, backend, quality, source, int(anchor), int(negative), _now()))
            db.execute("UPDATE persons SET updated_at=? WHERE id=?", (_now(), person_id))
            return int(cursor.lastrowid)

    def exemplars(self, *, backend: str, dim: int, negative: bool | None = None) -> list[dict]:
        query = "SELECT person_id,emb,dim,backend,quality,source,anchor,negative FROM exemplars WHERE backend=? AND dim=?"
        params: list = [backend, dim]
        if negative is not None:
            query += " AND negative=?"
            params.append(int(negative))
        with self._lock, self._connect() as db:
            rows = db.execute(query, params).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["embedding"] = self._vector(item.pop("emb"), item["dim"])
            result.append(item)
        return result

    def add_unknown(self, embedding, *, backend: str, threshold: float) -> tuple[str, int]:
        vector, dim = self._blob(embedding)
        now = _now()
        with self._lock, self._connect() as db:
            rows = db.execute("SELECT id,centroid,dim,n FROM unknowns WHERE backend=? AND dim=?", (backend, dim)).fetchall()
            best_id, best_score = None, -1.0
            for row in rows:
                score = float(np.dot(self._vector(row["centroid"], dim), self._vector(vector, dim)))
                if score > best_score:
                    best_id, best_score = row["id"], score
            if best_id is not None and best_score >= threshold:
                row = db.execute("SELECT centroid,n FROM unknowns WHERE id=?", (best_id,)).fetchone()
                count = int(row["n"])
                centroid = normalize_embedding(self._vector(row["centroid"], dim) * count + self._vector(vector, dim))
                db.execute("UPDATE unknowns SET centroid=?,n=?,last_seen=? WHERE id=?",
                           (centroid.astype("<f4").tobytes(), count + 1, now, best_id))
                return best_id, count + 1
            unknown_id = "unknown_" + uuid.uuid4().hex[:8]
            db.execute("INSERT INTO unknowns(id,centroid,dim,backend,n,first_seen,last_seen) VALUES(?,?,?,?,?,?,?)",
                       (unknown_id, vector, dim, backend, 1, now, now))
            return unknown_id, 1

    def list_unknowns(self) -> list[dict]:
        with self._lock, self._connect() as db:
            rows = db.execute("SELECT id,n,first_seen,last_seen,backend,dim FROM unknowns ORDER BY last_seen DESC").fetchall()
            return [dict(row) for row in rows]

    def unknown_vectors(self, *, backend: str, dim: int) -> list[dict]:
        with self._lock, self._connect() as db:
            rows = db.execute("SELECT id,centroid,n FROM unknowns WHERE backend=? AND dim=?", (backend, dim)).fetchall()
        return [{"id": row["id"], "n": row["n"], "embedding": self._vector(row["centroid"], dim)} for row in rows]

    def record_sighting(self, *, person_id: str | None, unknown_id: str | None,
                        label: str, camera: str, track_id: str,
                        similarity: float | None = None, snapshot_path: str | None = None) -> int:
        # Snapshots are intentionally disabled in this release; the column is
        # retained for a future explicit-consent feature.
        with self._lock, self._connect() as db:
            cursor = db.execute("INSERT INTO sightings(person_id,unknown_id,label,camera,track_id,similarity,ts,snapshot_path) VALUES(?,?,?,?,?,?,?,?)",
                                (person_id, unknown_id, label, camera, str(track_id), similarity, _now(), snapshot_path))
            return int(cursor.lastrowid)

    def sightings_for_unknown(self, unknown_id: str) -> int:
        with self._lock, self._connect() as db:
            return int(db.execute("SELECT count(*) FROM sightings WHERE unknown_id=?", (unknown_id,)).fetchone()[0])

    def promote_unknown(self, unknown_id: str, name: str) -> dict:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM unknowns WHERE id=?", (unknown_id,)).fetchone()
            if row is None:
                raise KeyError("unknown cluster not found")
            # Inline insertion shares the transaction and keeps promotion atomic.
            now = _now()
            clean_name = " ".join(str(name or "").split())
            if not clean_name or len(clean_name) > 80:
                raise ValueError("person name must contain 1–80 characters")
            existing = db.execute("SELECT id FROM persons WHERE name=? COLLATE NOCASE", (clean_name,)).fetchone()
            if existing:
                person_id = existing["id"]
            else:
                person_id = uuid.uuid4().hex
                db.execute("INSERT INTO persons(id,name,consent,profile_json,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                           (person_id, clean_name, 1, "{}", now, now))
            db.execute("INSERT INTO exemplars(person_id,emb,dim,backend,quality,source,anchor,negative,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                       (person_id, row["centroid"], row["dim"], row["backend"], 0.6,
                        "unknown-promotion", 1, 0, now))
            db.execute("UPDATE sightings SET person_id=?,unknown_id=NULL,label=? WHERE unknown_id=?",
                       (person_id, clean_name, unknown_id))
            db.execute("DELETE FROM unknowns WHERE id=?", (unknown_id,))
            return self.get_person(person_id, db=db)

    def correct_identity(self, *, track_id: str, claimed: str, correct: str,
                         person_id: str, embedding, backend: str, quality: float) -> None:
        vector, dim = self._blob(embedding)
        now = _now()
        with self._lock, self._connect() as db:
            person = db.execute("SELECT id FROM persons WHERE id=?", (person_id,)).fetchone()
            if not person:
                raise KeyError("correct person not found")
            db.execute("INSERT INTO exemplars(person_id,emb,dim,backend,quality,source,anchor,negative,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                       (person_id, vector, dim, backend, float(quality), "user-correction", 1, 1, now))
            db.execute("INSERT INTO identity_corrections(track_id,claimed_label,correct_label,ts,applied_action) VALUES(?,?,?,?,?)",
                       (str(track_id), claimed, correct, now, "negative-exemplar-and-threshold+0.02"))
            db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                       (f"threshold_offset:{person_id}", str(self.threshold_offset(person_id, db=db) + 0.02)))

    def threshold_offset(self, person_id: str, *, db=None) -> float:
        if db is None:
            with self._connect() as connection:
                return self.threshold_offset(person_id, db=connection)
        row = db.execute("SELECT value FROM settings WHERE key=?", (f"threshold_offset:{person_id}",)).fetchone()
        return float(row[0]) if row else 0.0

    def sightings_for_person(self, person_id: str) -> list[dict]:
        with self._lock, self._connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT label,camera,track_id,similarity,ts FROM sightings WHERE person_id=? ORDER BY ts DESC LIMIT 100",
                (person_id,)).fetchall()]

    def delete_person(self, person_id: str) -> bool:
        with self._lock, self._connect() as db:
            cursor = db.execute("DELETE FROM persons WHERE id=?", (person_id,))
            db.execute("DELETE FROM settings WHERE key=?", (f"threshold_offset:{person_id}",))
            return cursor.rowcount > 0

    def prune_adaptive(self, person_id: str, *, cap: int = 60) -> int:
        """Prune lowest-quality non-anchor positives while retaining all anchors."""
        with self._lock, self._connect() as db:
            total = int(db.execute(
                "SELECT count(*) FROM exemplars WHERE person_id=? AND negative=0", (person_id,)).fetchone()[0])
            excess = total - max(1, int(cap))
            if excess <= 0:
                return 0
            rows = db.execute(
                "SELECT id FROM exemplars WHERE person_id=? AND negative=0 AND anchor=0 "
                "ORDER BY quality ASC,created_at ASC LIMIT ?", (person_id, excess)).fetchall()
            if not rows:
                return 0
            ids = [int(row["id"]) for row in rows]
            db.executemany("DELETE FROM exemplars WHERE id=? AND anchor=0", ((value,) for value in ids))
            return len(ids)

    def adaptive_rows(self, person_id: str, *, backend: str, dim: int) -> list[dict]:
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT id,emb,dim,quality FROM exemplars WHERE person_id=? AND backend=? "
                "AND dim=? AND anchor=0 AND negative=0", (person_id, backend, dim)).fetchall()
        return [{"id": row["id"], "quality": row["quality"],
                 "embedding": self._vector(row["emb"], dim)} for row in rows]

    def remove_exemplar(self, exemplar_id: int) -> bool:
        with self._lock, self._connect() as db:
            cursor = db.execute("DELETE FROM exemplars WHERE id=? AND anchor=0 AND negative=0",
                                (int(exemplar_id),))
            return cursor.rowcount > 0

    def merge_unknowns(self, keep_id: str, merge_id: str) -> bool:
        if keep_id == merge_id:
            return False
        with self._lock, self._connect() as db:
            left = db.execute("SELECT * FROM unknowns WHERE id=?", (keep_id,)).fetchone()
            right = db.execute("SELECT * FROM unknowns WHERE id=?", (merge_id,)).fetchone()
            if not left or not right or left["backend"] != right["backend"] or left["dim"] != right["dim"]:
                return False
            count = int(left["n"] + right["n"])
            centroid = normalize_embedding(
                self._vector(left["centroid"], left["dim"]) * left["n"] +
                self._vector(right["centroid"], right["dim"]) * right["n"])
            db.execute("UPDATE unknowns SET centroid=?,n=?,first_seen=?,last_seen=? WHERE id=?",
                       (centroid.astype("<f4").tobytes(), count,
                        min(left["first_seen"], right["first_seen"]),
                        max(left["last_seen"], right["last_seen"]), keep_id))
            db.execute("UPDATE sightings SET unknown_id=? WHERE unknown_id=?", (keep_id, merge_id))
            db.execute("DELETE FROM unknowns WHERE id=?", (merge_id,))
            return True

    def expire_unknowns(self, *, days: int = 30) -> int:
        days = max(1, min(3650, int(days)))
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._lock, self._connect() as db:
            cursor = db.execute(
                "DELETE FROM unknowns WHERE snapshot_path IS NULL "
                "AND last_seen < ?", (cutoff,))
            return cursor.rowcount
