"""Local food log with atomic writes and conflict-aware undo."""
from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from datetime import date

from memory import config_manager as config
from core import undo, outcome

_lock = threading.RLock()
MAX_ROWS = 5000


def _path(): return config.CONFIG_DIR / "food_log.json"


def _read():
    path = _path()
    if not path.exists(): return []
    if path.stat().st_size > 2_000_000: raise ValueError("Food log exceeds the safety limit")
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise ValueError("Food log is invalid; original was preserved")
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"id", "day", "food", "kcal", "estimate"}:
            raise ValueError("Food log is invalid; original was preserved")
        if not isinstance(row["kcal"], int) or not 0 <= row["kcal"] <= 5000:
            raise ValueError("Food log is invalid; original was preserved")
    return rows


def _write(rows):
    path = _path(); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=path.parent, encoding="utf-8", delete=False) as f:
            tmp = f.name; json.dump(rows, f, ensure_ascii=False, indent=2); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
        if _read() != rows: raise IOError("Food log read-back mismatch")
    finally:
        if tmp and os.path.exists(tmp): os.unlink(tmp)


def add(food: str, kcal: int, estimate: bool = False, day: str | None = None):
    food = " ".join(str(food or "").split())
    if not 2 <= len(food) <= 120: raise ValueError("Food description must have 2–120 characters")
    kcal = int(kcal)
    if not 0 <= kcal <= 5000: raise ValueError("Calories must be between 0 and 5000")
    day = day or date.today().isoformat()
    date.fromisoformat(day)
    with _lock:
        before = _read()
        if len(before) >= MAX_ROWS: raise ValueError("Food log is full")
        row = {"id": uuid.uuid4().hex[:12], "day": day, "food": food,
               "kcal": kcal, "estimate": bool(estimate)}
        after = before + [row]; _write(after)
    def revert():
        with _lock:
            current = _read()
            if current != after: return outcome.failed("food_undo", "Food log changed; no entries were removed")
            _write(before)
        return outcome.done("food_undo")
    undo.push_undo(f"food log {row['food'][:40]}", revert)
    return row


def list_day(day: str | None = None):
    day = day or date.today().isoformat(); date.fromisoformat(day)
    with _lock:
        rows = [dict(row) for row in _read() if row["day"] == day]
    return {"day": day, "items": rows, "total_kcal": sum(x["kcal"] for x in rows)}


def remove(item_id: str):
    with _lock:
        before = _read(); row = next((x for x in before if x["id"] == item_id), None)
        if row is None: raise KeyError("Food entry not found")
        after = [x for x in before if x["id"] != item_id]; _write(after)
    def revert():
        with _lock:
            current = _read()
            if current != after: return outcome.failed("food_undo", "Food log changed; entry left removed")
            _write(before)
        return outcome.done("food_undo")
    undo.push_undo(f"remove food {row['food'][:40]}", revert)
    return row


def adjust(item_id: str, kcal: int):
    kcal = int(kcal)
    if not 0 <= kcal <= 5000: raise ValueError("Calories must be between 0 and 5000")
    with _lock:
        before = _read(); index = next((i for i, row in enumerate(before) if row["id"] == item_id), None)
        if index is None: raise KeyError("Food entry not found")
        after = [dict(row) for row in before]; after[index]["kcal"] = kcal; after[index]["estimate"] = True
        _write(after)
    def revert():
        with _lock:
            if _read() != after: return outcome.failed("food_undo", "Food log changed; adjustment left untouched")
            _write(before)
        return outcome.done("food_undo")
    undo.push_undo(f"adjust food calories {item_id}", revert)
    return after[index]
