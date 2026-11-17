"""Exact, verified text replacement with guarded session undo."""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from core import outcome, undo

_MAX_BYTES = 10 * 1024 * 1024


def _atomic_write(path: Path, data: bytes) -> None:
    fd, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp",
                                    dir=str(path.parent))
    temp = Path(raw_temp)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            os.chmod(temp, path.stat().st_mode)
        os.replace(temp, path)
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def edit_block(parameters: dict, **_context) -> str:
    """Replace an exact text block only when its occurrence count is expected."""
    p = parameters or {}
    try:
        raw_path = str(p.get("path", "")).strip().strip('"')
        find = p.get("find")
        replacement = p.get("replace")
        expected = p.get("expected_replacements")
        if not raw_path or not isinstance(find, str) or not find:
            raise ValueError("Informe path e um bloco find não vazio.")
        if not isinstance(replacement, str):
            raise ValueError("replace precisa ser texto.")
        if isinstance(expected, bool) or not isinstance(expected, int) or expected < 1:
            raise ValueError("expected_replacements precisa ser um inteiro positivo.")
        supplied_path = Path(raw_path).expanduser()
        if supplied_path.is_symlink():
            raise ValueError("O destino precisa ser um arquivo regular, não um link simbólico.")
        path = supplied_path.resolve(strict=True)
        if not path.is_file():
            raise ValueError("O destino precisa ser um arquivo regular.")
        before = path.read_bytes()
        if len(before) > _MAX_BYTES:
            raise ValueError("Arquivo acima do limite de edição de 10 MiB.")
        encoding = "utf-8-sig" if before.startswith(b"\xef\xbb\xbf") else "utf-8"
        text = before.decode(encoding)
        count = text.count(find)
        if count != expected:
            reason = ("Bloco ambíguo" if count > 1 else "Bloco não encontrado"
                      if count == 0 else "Quantidade encontrada difere do esperado")
            return outcome.failed("edit_block", reason, expected=expected, found=count)
        updated = text.replace(find, replacement)
        after = updated.encode(encoding)
        if after == before:
            return outcome.failed("edit_block", "A substituição não alteraria o arquivo.")
        _atomic_write(path, after)
        if path.read_bytes() != after:
            _atomic_write(path, before)
            return outcome.failed("edit_block", "A releitura não confirmou a gravação.")
        digest = hashlib.sha256(after).hexdigest()

        def restore() -> str:
            try:
                current = path.read_bytes()
                if hashlib.sha256(current).hexdigest() != digest:
                    return outcome.failed("edit_block_undo", "O arquivo mudou após a edição; preservado.")
                _atomic_write(path, before)
                return outcome.done("edit_block_undo", restored=True)
            except OSError as exc:
                return outcome.failed("edit_block_undo", str(exc))

        undo.push_undo(f"Edição exata: {path.name}", restore)
        return outcome.done("edit_block", path=str(path), replacements=count,
                            verified=path.read_bytes() == after)
    except UnicodeDecodeError:
        return outcome.failed("edit_block", "O arquivo não é texto UTF-8.")
    except (OSError, ValueError) as exc:
        return outcome.failed("edit_block", str(exc))


TOOL = {
    "name": "edit_block",
    "description": "Replace an exact text block in a local UTF-8 file. Requires the expected replacement count; refuses missing or ambiguous matches and supports guarded undo.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "path": {"type": "STRING"},
            "find": {"type": "STRING"},
            "replace": {"type": "STRING"},
            "expected_replacements": {"type": "INTEGER"},
        },
        "required": ["path", "find", "replace", "expected_replacements"],
    },
    "handler": edit_block,
    "tier": "core",
    "brief": "Verified exact text replacement with ambiguity guard and undo.",
}
