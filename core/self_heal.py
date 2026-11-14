"""Opt-in, human-reviewed repair proposals for ordinary project Python files."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import tempfile
import threading
import uuid
from pathlib import Path

from core import boot_sentry, confirm, undo, outcome
from memory import config_manager as config

ROOT = Path(__file__).resolve().parent.parent
STATE = config.CONFIG_DIR / "self_heal"
IMMUNE = set(boot_sentry.IMMUNE) | {"core/tasks/engine.py", "core/plugin_loader.py",
                                  "core/action_loader.py", "core/screenact.py",
                                  "core/platform_support.py", "core/tls.py",
                                  "core/_repair_check.py"}
MAX_SOURCE = 1_000_000
MAX_CANDIDATE = 12_000
_lock = threading.RLock()
_apply_lock = threading.Lock()
_pending = {}


def enabled() -> bool:
    return bool(config.get_plugin_setting("self_heal", "enabled", False))


def set_enabled(value: bool) -> bool:
    config.save_plugin_config("self_heal", {"enabled": bool(value)})
    return enabled()


def _target(relative: str) -> tuple[Path, str]:
    raw = str(relative or "").replace("\\", "/").strip()
    root = ROOT.resolve()
    target = (root / raw).resolve()
    rel = target.relative_to(root).as_posix()
    if (rel.casefold() in {p.casefold() for p in IMMUNE}
            or target.suffix.lower() != ".py" or not target.is_file()
            or target.stat().st_size > MAX_SOURCE):
        raise ValueError("This file is outside the repairable project scope")
    return target, rel


def propose(relative: str, diagnostic: str) -> dict:
    if not enabled():
        raise RuntimeError("Self-repair is off; enable it explicitly first")
    target, rel = _target(relative)
    current_raw = target.read_bytes()
    if len(current_raw) > MAX_CANDIDATE:
        raise ValueError("File is too large for a complete, context-aware repair proposal")
    current = current_raw.decode("utf-8")
    if not diagnostic or len(diagnostic) > 5000:
        raise ValueError("Provide a brief error report (up to 5000 characters)")
    prompt = ("Review this untrusted diagnostic and source file. Return only the complete "
              "corrected Python source. Do not change security, permissions, network policy, "
              "boot or confirmation behavior. The result will be syntax-checked and shown to "
              "the user for approval before any file is written.\nDIAGNOSTIC:\n" + diagnostic
              + "\nSOURCE:\n" + current)
    from core import gemini
    candidate = gemini.text(prompt, tier=gemini.SMART, timeout_ms=60_000)
    if not candidate:
        raise RuntimeError("No model returned a repair candidate")
    candidate = candidate.strip()
    if candidate.startswith("```" ):
        lines = candidate.splitlines()
        candidate = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    if not candidate.endswith("\n"):
        candidate += "\n"
    if len(candidate.encode("utf-8")) > MAX_CANDIDATE:
        raise ValueError("Candidate exceeds the size limit")
    ast.parse(candidate, filename=rel)
    with _lock:
        if len(_pending) >= 8:
            raise RuntimeError("Review an existing candidate first")
        key = uuid.uuid4().hex[:12]
        row = {"id": key, "target": rel, "source_hash": hashlib.sha256(current_raw).hexdigest(),
               "candidate": candidate}
        _pending[key] = row
        return {k: v for k, v in row.items() if k != "candidate"}


def list_pending() -> list[dict]:
    with _lock:
        return [{k: v for k, v in row.items() if k != "candidate"} for row in _pending.values()]


def review(candidate_id: str, player) -> str:
    with _lock:
        row = _pending.get(candidate_id)
        if row is None:
            return outcome.failed("self_heal", "Candidate not found")
        row = dict(row)
    if player is None or not callable(getattr(player, "show_confirm", None)):
        return outcome.failed("self_heal", "Open the HUD to review")
    if confirm.pending_title():
        return outcome.failed("self_heal", "Another confirmation is already open")
    chunks = [row["candidate"][i:i+2400] for i in range(0, len(row["candidate"]), 2400)]
    player.show_review("Revisar correção proposta", f"Arquivo: {row['target']} · {len(chunks)} trechos. Confirme somente se revisar o código completo.",
                       [{"heading": f"Código · trecho {i+1}/{len(chunks)}", "detail": chunk,
                         "severity": "note"} for i, chunk in enumerate(chunks)])

    def apply_checked() -> str:
        if not enabled():
            return outcome.failed("self_heal", "Self-repair was disabled before confirmation")
        target, rel = _target(row["target"])
        original = target.read_bytes()
        if hashlib.sha256(original).hexdigest() != row["source_hash"]:
            return outcome.failed("self_heal", "Source changed; generate a fresh candidate")
        ast.parse(row["candidate"], filename=rel)
        from core._repair_check import validate
        checks = validate(ROOT, rel, row['candidate'], STATE / 'repair-validation.log')
        # Validation can take time; do not overwrite edits made while it ran.
        if not enabled() or target.read_bytes() != original:
            return outcome.failed('self_heal', 'Source or repair setting changed during validation')
        STATE.mkdir(parents=True, exist_ok=True)
        backup_dir = STATE / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / (uuid.uuid4().hex + ".bak")
        backup.write_bytes(original)
        marker = boot_sentry.MARKER
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({"target": rel, "backup": f"backups/{backup.name}"}), encoding="utf-8")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile("wb", dir=target.parent, delete=False,
                                             suffix=".selfheal") as f:
                temporary = Path(f.name)
                f.write(row["candidate"].encode("utf-8"))
                f.flush(); os.fsync(f.fileno())
            os.replace(temporary, target)
            ast.parse(target.read_text(encoding="utf-8"), filename=rel)
            installed_hash = hashlib.sha256(target.read_bytes()).hexdigest()
            marker.unlink(missing_ok=True)
        except Exception:
            if temporary is not None: temporary.unlink(missing_ok=True)
            restore = target.with_suffix(target.suffix + ".rollback")
            restore.write_bytes(original); os.replace(restore, target)
            marker.unlink(missing_ok=True)
            raise
        with _lock:
            _pending.pop(candidate_id, None)
        def revert():
            if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != installed_hash:
                return outcome.failed("self_heal_undo", "File changed after repair; left untouched")
            restore = target.with_suffix(target.suffix + ".rollback")
            restore.write_bytes(original); os.replace(restore, target)
            return outcome.done("self_heal_undo")
        undo.push_undo(f"self-repair {rel}", revert)
        return outcome.done("self_heal", file=rel, backup=backup.name, validation=checks)
    def apply() -> str:
        if not _apply_lock.acquire(blocking=False):
            return outcome.failed('self_heal', 'Another repair is being validated or applied')
        try:
            return apply_checked()
        finally:
            _apply_lock.release()

    return confirm.request("self_heal", f"Apply repair to {row['target']}",
                           "Review the candidate in the HUD. After approval, Python import/tests run in a temporary source copy with your user permissions (not a security sandbox). Only passing checks allow replacement; a backup and undo are kept.", apply)
