"""Small local SQLite audit trail for tool and action calls."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.RLock()
_SENSITIVE = re.compile(r"(?:secret|token|password|passwd|api.?key|authorization|cookie|credential)", re.I)
_PRIVATE_PAYLOADS = {"text", "content", "body", "prompt", "transcript", "message",
                     "value", "command", "query", "script"}
_STATUSES = ("done", "unverified", "failed", "ask", "started")
_MAX_ROWS = 50_000


def _db_path() -> Path:
    configured = os.environ.get("JINX_AUDIT_DB", "").strip()
    return Path(configured).expanduser() if configured else Path(__file__).resolve().parents[1] / "memory" / "audit.db"


def _sanitize(value: Any, key: str = "", depth: int = 0) -> Any:
    if _SENSITIVE.search(key):
        return "[REDACTED]"
    if depth >= 8:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        return {str(k)[:100]: _sanitize(v, str(k), depth + 1)
                for k, v in list(value.items())[:200]}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item, key, depth + 1) for item in value[:200]]
    if isinstance(value, str):
        if key.casefold() in _PRIVATE_PAYLOADS:
            return f"[OMITTED {len(value)} chars]"
        return value[:2000]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:500]


def _status(result: Any) -> str:
    text = str(result or "")
    for status in _STATUSES:
        if text.startswith(f"status={status} "):
            return status
    return "unknown"


def record_tool_call(kind: str, name: str, parameters: dict | None,
                     result: Any, duration_ms: float) -> bool:
    """Persist metadata and redacted arguments; never persist tool output text."""
    try:
        path = _db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        args = json.dumps(_sanitize(parameters or {}), ensure_ascii=False,
                          separators=(",", ":"), sort_keys=True)
        with _LOCK, closing(sqlite3.connect(path, timeout=10)) as db, db:
            db.execute("PRAGMA busy_timeout=10000")
            db.execute("""CREATE TABLE IF NOT EXISTS tool_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                name TEXT NOT NULL,
                parameters_json TEXT NOT NULL,
                outcome TEXT NOT NULL,
                duration_ms REAL NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_tool_calls_created_at "
                       "ON tool_calls(created_at)")
            db.execute("INSERT INTO tool_calls(created_at,kind,name,parameters_json,outcome,duration_ms) "
                       "VALUES(?,?,?,?,?,?)",
                       (datetime.now(timezone.utc).isoformat(), str(kind)[:40], str(name)[:120],
                        args, _status(result), max(0.0, float(duration_ms))))
            # Keep the local store bounded while preserving the most recent history.
            db.execute("DELETE FROM tool_calls WHERE id NOT IN "
                       "(SELECT id FROM tool_calls ORDER BY id DESC LIMIT ?)", (_MAX_ROWS,))
        return True
    except Exception:
        # Logging must never turn a successfully completed action into a failure.
        return False


def recent(limit: int = 100) -> list[dict[str, Any]]:
    """Read recent audit metadata without exposing raw tool output."""
    count = max(1, min(int(limit), 1000))
    path = _db_path()
    if not path.exists():
        return []
    with _LOCK, closing(sqlite3.connect(path, timeout=10)) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute("SELECT id,created_at,kind,name,parameters_json,outcome,duration_ms "
                          "FROM tool_calls ORDER BY id DESC LIMIT ?", (count,)).fetchall()
    return [dict(row) for row in rows]
