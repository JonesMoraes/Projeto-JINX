"""Full-path filesystem operations with verification and reversible mutations."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
import uuid
from pathlib import Path

from core import outcome, undo

_READ_LIMIT = 1_000_000
_UNDO_LIMIT = 16 * 1024 * 1024
_LIST_LIMIT = 500
_TRASH = Path(__file__).resolve().parents[1] / "memory" / "fs_trash"


def _path(value: str, *, require=False) -> Path:
    raw = str(value or "").strip().strip('"')
    if not raw:
        raise ValueError("path is required")
    target = Path(raw).expanduser()
    if require and target.is_symlink():
        raise ValueError("refusing to follow a symbolic link for this operation")
    return target.resolve(strict=True) if require else target.absolute()


def _atomic_write(path: Path, data: bytes) -> None:
    if path.is_symlink():
        raise ValueError("refusing to write through a symbolic link")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(raw)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            os.chmod(temp, stat.S_IMODE(path.stat().st_mode))
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def _remove_if_unchanged(path: Path, digest: str, label: str) -> str:
    try:
        if path.is_symlink() or not path.is_file() or _digest(path) != digest:
            return outcome.failed("fs_undo", "Target changed after the operation; left untouched.",
                                  target=label)
        path.unlink()
        return outcome.done("fs_undo", removed=True, target=label)
    except OSError as exc:
        return outcome.failed("fs_undo", str(exc), target=label)


def _restore_deleted(path: Path, backup: Path, digest: str) -> str:
    try:
        if path.exists():
            return outcome.failed("fs_undo", "Original path now exists; preserved both copies.",
                                  path=str(path))
        if not backup.is_file() or _digest(backup) != digest:
            return outcome.failed("fs_undo", "Trash copy is missing or changed.", path=str(path))
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(backup), str(path))
        return outcome.done("fs_undo", restored=True, path=str(path))
    except OSError as exc:
        return outcome.failed("fs_undo", str(exc), path=str(path))


def _undo_mkdir(path: Path) -> str:
    try:
        if not path.is_dir() or any(path.iterdir()):
            return outcome.failed("fs_mkdir_undo", "Directory is no longer empty; left intact.",
                                  path=str(path))
        path.rmdir()
        return outcome.done("fs_mkdir_undo", path=str(path))
    except OSError as exc:
        return outcome.failed("fs_mkdir_undo", str(exc), path=str(path))


def _perform(p: dict) -> str:
    action = str(p.get("action", "")).lower()
    path = _path(p.get("path", ""), require=action in {"read", "list", "stat", "delete", "chmod"})
    if action == "list":
        if not path.is_dir():
            raise ValueError("path is not a directory")
        rows = []
        for child in sorted(path.iterdir(), key=lambda item: item.name.casefold())[:_LIST_LIMIT]:
            try:
                info = child.stat()
                rows.append({"name": child.name, "type": "directory" if child.is_dir() else "file",
                             "size": info.st_size, "modified": info.st_mtime})
            except OSError:
                continue
        return outcome.done("fs_list", path=str(path), entries=outcome.untrusted(
            "filesystem-list", json.dumps(rows, ensure_ascii=False)), count=len(rows),
            truncated=len(rows) == _LIST_LIMIT)
    if action == "read":
        if not path.is_file() or path.stat().st_size > _READ_LIMIT:
            raise ValueError("read requires a file no larger than 1 MiB")
        data = path.read_bytes()
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            return outcome.done("fs_read", path=str(path), encoding="base64",
                                data=__import__("base64").b64encode(data).decode("ascii"))
        return outcome.done("fs_read", path=str(path), text=outcome.untrusted("local-file", text))
    if action == "stat":
        info = path.stat()
        return outcome.done("fs_stat", path=str(path), is_dir=path.is_dir(), size=info.st_size,
                            modified=info.st_mtime, mode=oct(stat.S_IMODE(info.st_mode)))
    if action == "mkdir":
        path.mkdir(parents=bool(p.get("parents", True)), exist_ok=False)
        undo.push_undo(f"Create directory: {path}", lambda: _undo_mkdir(path))
        return outcome.done("fs_mkdir", path=str(path), verified=path.is_dir())
    if action in {"create_file", "write", "append"}:
        if path.is_symlink():
            raise ValueError("refusing to modify a symbolic link")
        content = str(p.get("content", "")).encode("utf-8")
        if len(content) > _UNDO_LIMIT:
            raise ValueError("content exceeds 16 MiB")
        if action == "create_file" and path.exists():
            raise FileExistsError("path already exists")
        existed = path.exists()
        if path.is_file() and path.stat().st_size > _UNDO_LIMIT:
            raise ValueError("existing file exceeds the 16 MiB reversible-edit limit")
        before = path.read_bytes() if path.is_file() else None
        if action == "append":
            prior = before or b""
            after = prior + content
        else:
            after = content
        if len(after) > _UNDO_LIMIT:
            raise ValueError("result exceeds 16 MiB")
        _atomic_write(path, after)
        digest = hashlib.sha256(after).hexdigest()
        if path.read_bytes() != after:
            raise OSError("write verification failed")
        if not existed:
            undo.push_undo(f"Remove created file: {path}",
                           lambda: _remove_if_unchanged(path, digest, str(path)))
        else:
            def restore() -> str:
                if not path.is_file() or _digest(path) != digest:
                    return outcome.failed("fs_write_undo", "File changed after write; left untouched.")
                _atomic_write(path, before)
                return outcome.done("fs_write_undo", restored=True)
            undo.push_undo(f"Restore file: {path}", restore)
        return outcome.done("fs_write", action=action, path=str(path), bytes=len(after), verified=True)
    if action == "delete":
        if not path.is_file() or path.is_symlink() or path.stat().st_size > _UNDO_LIMIT:
            raise ValueError("delete supports regular files up to 16 MiB; directories are not recursively deleted")
        _TRASH.mkdir(parents=True, exist_ok=True)
        backup = _TRASH / f"{uuid.uuid4().hex}-{path.name}"
        digest = _digest(path)
        shutil.move(str(path), str(backup))
        undo.push_undo(f"Restore deleted file: {path}",
                       lambda: _restore_deleted(path, backup, digest))
        return outcome.done("fs_delete", path=str(path), recoverable_copy=str(backup),
                            verified=not path.exists() and backup.is_file())
    if action in {"move", "rename", "copy"}:
        destination = _path(p.get("destination", ""))
        if not path.exists() or path.is_symlink():
            raise ValueError("source does not exist or is a symbolic link")
        if path.is_dir() and any(path.iterdir()):
            raise ValueError("move/rename supports only files or empty directories")
        if destination.exists():
            raise FileExistsError("destination already exists")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if action == "copy":
            if not path.is_file():
                raise ValueError("copy currently supports regular files")
            shutil.copy2(path, destination)
            digest = _digest(destination)
            undo.push_undo(f"Remove copied file: {destination}",
                           lambda: _remove_if_unchanged(destination, digest, str(destination)))
            verified = _digest(path) == digest == _digest(destination)
        else:
            shutil.move(str(path), str(destination))
            digest = _digest(destination) if destination.is_file() else ""
            moved_directory = destination.is_dir()
            def restore_move() -> str:
                if path.exists() or not destination.exists():
                    return outcome.failed("fs_move_undo", "Source/destination changed; left untouched.")
                if digest and (not destination.is_file() or _digest(destination) != digest):
                    return outcome.failed("fs_move_undo", "Moved file changed; left untouched.")
                if moved_directory and (not destination.is_dir() or any(destination.iterdir())):
                    return outcome.failed("fs_move_undo", "Moved directory changed; left untouched.")
                shutil.move(str(destination), str(path))
                return outcome.done("fs_move_undo", restored=True)
            undo.push_undo(f"Move back: {destination}", restore_move)
            verified = destination.exists() and not path.exists()
        if not verified:
            return outcome.unverified("fs_transfer", "Transfer verification failed.",
                                      source=str(path), destination=str(destination))
        return outcome.done("fs_transfer", action=action, source=str(path),
                            destination=str(destination), verified=True)
    if action == "chmod":
        old_mode = stat.S_IMODE(path.stat().st_mode)
        mode = int(str(p.get("mode", "")), 8)
        if not 0 <= mode <= 0o777:
            raise ValueError("mode must be an octal permission between 000 and 777")
        os.chmod(path, mode)
        if stat.S_IMODE(path.stat().st_mode) != mode:
            os.chmod(path, old_mode)
            return outcome.failed("fs_chmod", "Permission change did not verify.", path=str(path))
        undo.push_undo(f"Restore permissions: {path}", lambda: _restore_mode(path, mode, old_mode))
        return outcome.done("fs_chmod", path=str(path), mode=oct(mode), verified=True)
    raise ValueError("unsupported filesystem action")


def _restore_mode(path: Path, expected: int, old: int) -> str:
    try:
        if stat.S_IMODE(path.stat().st_mode) != expected:
            return outcome.failed("fs_chmod_undo", "Permissions changed after operation.")
        os.chmod(path, old)
        return outcome.done("fs_chmod_undo", mode=oct(old))
    except OSError as exc:
        return outcome.failed("fs_chmod_undo", str(exc))


def fs_total(parameters: dict, **_context) -> str:
    try:
        return _perform(parameters or {})
    except (OSError, ValueError, TypeError) as exc:
        return outcome.failed("fs_total", str(exc))


TOOL = {
    "name": "fs_total",
    "description": "Create/read/write/append/delete/move/copy/rename/list/stat files and directories by full path, including shared paths; change permissions. Reversible changes register guarded undo. Deletes move files to JINX recovery storage; recursive directory deletion is not supported.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["list", "read", "stat", "mkdir", "create_file", "write", "append", "delete", "move", "rename", "copy", "chmod"]},
            "path": {"type": "STRING"}, "destination": {"type": "STRING"},
            "content": {"type": "STRING"}, "mode": {"type": "STRING"},
            "parents": {"type": "BOOLEAN"},
        },
        "required": ["action", "path"],
    },
    "handler": fs_total,
    "tier": "core",
    "brief": "Full-path file operations with recoverable deletes and guarded undo.",
}
