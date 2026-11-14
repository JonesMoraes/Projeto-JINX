"""Child updater: wait for JINX to exit, verify staged files, swap and rollback."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import time


def _alive(pid):
    try:
        import psutil
        return psutil.pid_exists(pid)
    except Exception:
        try: os.kill(pid, 0); return True
        except OSError: return False


def apply(root: Path, stage: Path, pid: int):
    root, stage = root.resolve(strict=True), stage.resolve(strict=True)
    state = (root / ".jinx_update").resolve()
    if state not in stage.parents: raise ValueError("staging path escaped updater state")
    manifest = json.loads((stage / "update-manifest.json").read_text(encoding="utf-8"))
    files = manifest.get("files")
    if not isinstance(files, list) or not files or len(files) > 3000: raise ValueError("invalid update manifest")
    deadline = time.monotonic() + 90
    while _alive(pid) and time.monotonic() < deadline: time.sleep(.25)
    if _alive(pid): raise TimeoutError("JINX process did not close")
    backup = state / "backups" / str(manifest.get("tag", "update"))
    backup.mkdir(parents=True, exist_ok=True)
    changed = []; marker_files = []; total_bytes = 0; planned = []
    try:
        for row in files:
            rel = PurePosixPath(str(row["path"]).replace("\\", "/"))
            if rel.is_absolute() or any(p in ("", ".", "..") for p in rel.parts): raise ValueError("unsafe path")
            folded = rel.as_posix().casefold()
            if (folded.startswith(("config/", "memory/", "logs/", "uploads/", ".git/", ".venv/", ".venv-local/", ".jinx_update/", "assets/third_party/"))
                    or folded in {"core/confirm.py", "core/undo.py", "core/boot_sentry.py",
                                  "core/self_heal.py", "core/update_apply.py", "memory/config_manager.py"}):
                raise ValueError("update includes protected user data")
            src = stage.joinpath(*rel.parts).resolve(strict=True)
            if stage not in src.parents or not src.is_file(): raise ValueError("staged file escaped its root")
            data = src.read_bytes()
            if len(data) != int(row["size"]) or hashlib.sha256(data).hexdigest() != row["sha256"]:
                raise ValueError("staged file hash mismatch")
            total_bytes += len(data)
            if len(data) > 20_000_000 or total_bytes > 500 * 1024 * 1024:
                raise ValueError("update file set exceeds limits")
            dest = (root / Path(*rel.parts)).resolve()
            if root not in dest.parents: raise ValueError("target escaped project root")
            if dest.suffix.lower() == ".py":
                import ast
                ast.parse(data.decode("utf-8"), filename=str(rel))
            old = dest.read_bytes() if dest.is_file() else None
            if old is not None:
                if len(old) > 20_000_000:
                    raise ValueError("existing target is too large for a bounded rollback backup")
                b = backup.joinpath(*rel.parts); b.parent.mkdir(parents=True, exist_ok=True); b.write_bytes(old)
                marker_files.append({"target": rel.as_posix(), "backup": str(b.relative_to(state)).replace("\\", "/")})
            else:
                marker_files.append({"target": rel.as_posix(), "created": True})
            planned.append((dest, data, old))
        marker = state / "pending-update.json"
        marker_tmp = marker.with_suffix(".tmp")
        marker_tmp.write_text(json.dumps({"tag": manifest.get("tag"), "files": marker_files}, indent=2), encoding="utf-8")
        os.replace(marker_tmp, marker)
        for dest, data, old in planned:
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(dest.name + ".jinx-update")
            tmp.write_bytes(data); os.replace(tmp, dest)
            changed.append((dest, old))
        (root / "logs").mkdir(parents=True, exist_ok=True)
        log = (root / "logs" / "update-helper.log").open("ab")
        try:
            env = dict(os.environ, JINX_UPDATE_ATTEMPT="1")
            subprocess.Popen([sys.executable, "-u", "main.py"], cwd=str(root), env=env,
                             stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        finally: log.close()
    except Exception:
        try: (state / "pending-update.json").unlink(missing_ok=True)
        except Exception: pass
        for dest, old in reversed(changed):
            try:
                if old is None: dest.unlink(missing_ok=True)
                else:
                    tmp = dest.with_name(dest.name + ".jinx-rollback")
                    tmp.write_bytes(old); os.replace(tmp, dest)
            except Exception: pass
        raise


if __name__ == "__main__":
    try:
        apply(Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]))
    except Exception as exc:
        print(f"Update failed: {type(exc).__name__}: {str(exc)[:240]}", flush=True)
        raise SystemExit(1) from None
