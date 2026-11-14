"""Rollback only an interrupted, explicitly approved self-heal transaction.

This module runs before Qt and model imports. It never edits boot/security files.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "config" / "self_heal"
MARKER = STATE / "pending.json"
UPDATE_MARKER = STATE / "pending-update.json"
IMMUNE = {"main.py", "ui.py", "setup.py", "core/boot_sentry.py",
          "core/self_heal.py", "core/confirm.py", "core/undo.py",
          "core/outcome.py", "memory/config_manager.py"}


def recover() -> bool:
    """Restore a backup left mid-transaction; return whether recovery ran."""
    restored = _recover_update()
    try:
        if not MARKER.is_file() or MARKER.stat().st_size > 4096:
            return restored
        row = json.loads(MARKER.read_text(encoding="utf-8"))
        rel = str(row.get("target", "")).replace("\\", "/")
        backup = (STATE / str(row.get("backup", ""))).resolve()
        target = (ROOT / rel).resolve()
        if (not rel or rel in IMMUNE or target == ROOT or ROOT not in target.parents
                or target.suffix.lower() != ".py" or STATE not in backup.parents
                or not backup.is_file() or backup.stat().st_size > 2_000_000):
            raise ValueError("invalid recovery marker")
        target.parent.mkdir(parents=True, exist_ok=True)
        replacement = target.with_suffix(target.suffix + ".recovery")
        replacement.write_bytes(backup.read_bytes())
        os.replace(replacement, target)
        MARKER.unlink(missing_ok=True)
        return True
    except Exception as exc:
        try:
            STATE.mkdir(parents=True, exist_ok=True)
            with (STATE / "boot-sentry.log").open("a", encoding="utf-8") as f:
                f.write(f"recovery blocked: {type(exc).__name__}\n")
        except Exception:
            pass
        return restored


def _recover_update() -> bool:
    if os.environ.get("JINX_UPDATE_ATTEMPT") == "1" or not UPDATE_MARKER.is_file():
        return False
    try:
        if UPDATE_MARKER.stat().st_size > 256000: raise ValueError("update marker too large")
        marker = json.loads(UPDATE_MARKER.read_text(encoding="utf-8"))
        files = marker.get("files")
        if not isinstance(files, list) or len(files) > 3000: raise ValueError("invalid update marker")
        for row in reversed(files):
            rel = str(row["target"]).replace("\\", "/")
            target = (ROOT / rel).resolve()
            folded = rel.casefold()
            if (not rel or target == ROOT or ROOT not in target.parents
                    or folded.startswith(("config/", "memory/", "logs/", "uploads/", ".git/", ".venv/", ".venv-local/", ".jinx_update/", "assets/third_party/"))
                    or folded in {"core/confirm.py", "core/undo.py", "core/boot_sentry.py",
                                  "core/self_heal.py", "core/update_apply.py", "memory/config_manager.py"}):
                raise ValueError("unsafe update rollback path")
            if row.get("created") is True:
                target.unlink(missing_ok=True)
            else:
                backup = (STATE / str(row["backup"])).resolve()
                if STATE not in backup.parents or not backup.is_file() or backup.stat().st_size > 20_000_000:
                    raise ValueError("invalid update backup")
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_name(target.name + ".update-rollback")
                tmp.write_bytes(backup.read_bytes()); os.replace(tmp, target)
        UPDATE_MARKER.unlink(missing_ok=True)
        return True
    except Exception as exc:
        try:
            STATE.mkdir(parents=True, exist_ok=True)
            with (STATE / "boot-sentry.log").open("a", encoding="utf-8") as f:
                f.write(f"update rollback blocked: {type(exc).__name__}\n")
        except Exception: pass
        return False


def mark_update_healthy() -> None:
    if os.environ.pop("JINX_UPDATE_ATTEMPT", None) == "1":
        try: UPDATE_MARKER.unlink(missing_ok=True)
        except Exception: pass
