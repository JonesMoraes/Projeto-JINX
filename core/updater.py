"""Opt-in, verified GitHub release staging and rollback-aware restart update."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import threading
import urllib.request
import zipfile

from memory import config_manager as config

ROOT = Path(__file__).resolve().parent.parent
REPO = "JonesMoraes/JINX-IA"
STATE = ROOT / ".jinx_update"
MAX_ARCHIVE = 300 * 1024 * 1024
MAX_EXPANDED = 500 * 1024 * 1024
_lock = threading.Lock()
_last_release = None


def enabled():
    return bool(config.get_plugin_setting("updater", "enabled", False))


def set_enabled(value):
    config.save_plugin_config("updater", {"enabled": bool(value)})
    return enabled()


def _request(url, timeout=12, max_bytes=2_000_000):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "JINX-IA-Updater/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes: raise ValueError("Response exceeds size limit")
    return data


def check_latest():
    if not enabled(): raise RuntimeError("Updates are off; opt in first")
    global _last_release
    body = json.loads(_request(f"https://api.github.com/repos/{REPO}/releases/latest"))
    if body.get("draft") or body.get("prerelease"):
        raise ValueError("Latest GitHub release is not stable")
    assets = []
    for asset in body.get("assets") or []:
        name = str(asset.get("name") or "")
        digest = str(asset.get("digest") or "")
        url = str(asset.get("browser_download_url") or "")
        if (re.fullmatch(r"jinx-update-[A-Za-z0-9._-]+\.zip", name)
                and re.fullmatch(r"sha256:[a-fA-F0-9]{64}", digest)
                and url.startswith("https://github.com/")):
            assets.append({"name": name, "digest": digest.split(":", 1)[1].lower(),
                           "url": url, "size": int(asset.get("size") or 0)})
    if not assets: raise ValueError("Release has no verified jinx-update ZIP asset")
    asset = min(assets, key=lambda row: row["size"])
    if not 0 < asset["size"] <= MAX_ARCHIVE: raise ValueError("Release asset size outside limits")
    release = {"tag": str(body.get("tag_name") or "")[:80],
               "name": str(body.get("name") or "")[:160],
               "page": str(body.get("html_url") or "")[:500],
               "asset": asset}
    _last_release = release
    return release


def _safe_path(name):
    path = PurePosixPath(str(name).replace("\\", "/"))
    if path.is_absolute() or not path.parts or any(p in ("", ".", "..") for p in path.parts):
        return None
    parts = path.parts
    # GitHub source archives wrap files in a repository/tag directory.
    root_name = parts[0].lower()
    rel = PurePosixPath(*parts[1:]) if len(parts) > 1 and (
        root_name == "jinx-ia" or root_name.startswith("jinx-ia-")
    ) else path
    if not rel.parts: return None
    text = rel.as_posix()
    folded = text.casefold()
    protected = ("config/", "memory/", "logs/", "uploads/", ".git/", ".venv/",
                 ".venv-local/", ".jinx_update/", "assets/third_party/")
    protected_code = {"core/confirm.py", "core/undo.py", "core/boot_sentry.py",
                      "core/self_heal.py", "core/update_apply.py", "memory/config_manager.py"}
    if folded.startswith(protected) or folded in {"config", "memory", "logs"} or folded in protected_code:
        return None
    if text == "core/update_apply.py": return None
    if not re.fullmatch(r"[A-Za-z0-9._/-]{1,240}", text): return None
    return rel


def stage(release=None):
    if not enabled(): raise RuntimeError("Updates are off; opt in first")
    release = release or check_latest()
    asset = release["asset"]
    if asset["size"] > MAX_ARCHIVE: raise ValueError("Release archive is too large")
    raw = _request(asset["url"], timeout=60, max_bytes=MAX_ARCHIVE)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != asset["digest"]: raise ValueError("Release asset SHA-256 mismatch")
    stage_dir = STATE / "staging" / re.sub(r"[^A-Za-z0-9._-]", "_", release["tag"])
    stage_dir.mkdir(parents=True, exist_ok=True)
    files = []; expanded = 0
    with zipfile.ZipFile(__import__("io").BytesIO(raw)) as archive:
        for item in archive.infolist():
            rel = _safe_path(item.filename)
            if rel is None or item.is_dir(): continue
            # Reject links and special files from the archive.
            mode = item.external_attr >> 16
            if mode and (mode & 0o170000) not in (0, 0o100000):
                raise ValueError("Release contains a non-regular file")
            if item.file_size > 20_000_000: continue
            expanded += item.file_size
            if expanded > MAX_EXPANDED or len(files) >= 3000: raise ValueError("Expanded archive exceeds limits")
            data = archive.read(item)
            target = stage_dir.joinpath(*rel.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            files.append({"path": rel.as_posix(), "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)})
    if not files: raise ValueError("Release archive had no eligible project files")
    manifest = {"tag": release["tag"], "page": release["page"], "asset_sha256": digest, "files": files}
    (stage_dir / "update-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"tag": release["tag"], "directory": str(stage_dir), "files": len(files),
            "expanded_bytes": expanded, "sha256": digest, "page": release["page"]}


def apply_after_restart(stage_dir, player):
    if not enabled(): raise RuntimeError("Updates are off")
    folder = Path(stage_dir).resolve(strict=True)
    if STATE.resolve() not in folder.parents: raise ValueError("Update staging path is outside JINX state")
    if not (folder / "update-manifest.json").is_file(): raise ValueError("Staged update manifest missing")
    log_path = ROOT / "logs" / "update-helper.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("ab")
    command = [sys.executable, "-m", "core.update_apply", str(ROOT), str(folder), str(os.getpid())]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        subprocess.Popen(command, cwd=str(ROOT), stdin=subprocess.DEVNULL,
                         stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
    finally:
        log.close()
    player.request_close()
    return "Update helper started. JINX will reopen after the checked file swap."
