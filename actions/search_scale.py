"""Concurrent, paginated filename/content search with ripgrep and Python fallback."""
from __future__ import annotations

import fnmatch
import json
import logging
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core import outcome

_EXCLUDED = {".git", ".jinx_runtime", ".venv", "venv", "node_modules",
             "__pycache__", ".tox", "dist", "build"}
_MAX_ROOTS = 16
_MAX_HITS = 10_000
_LOG = logging.getLogger(__name__)


def _roots(raw) -> list[Path]:
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, list):
        values = raw
    else:
        raise ValueError("roots must be a path or a list of paths")
    if not values or len(values) > _MAX_ROOTS:
        raise ValueError(f"provide between 1 and {_MAX_ROOTS} search roots")
    paths = []
    for value in values:
        path = Path(str(value)).expanduser().resolve(strict=True)
        if not path.is_dir() and not path.is_file():
            raise ValueError(f"not a file or directory: {path}")
        paths.append(path)
    return paths


def _fallback(root: Path, query: str, filename_pattern: str, ignore_case: bool,
              include_hidden: bool, cap: int) -> list[dict]:
    results = []
    needle = query.casefold() if ignore_case else query
    if root.is_file():
        files = [root]
        base = root.parent
    else:
        base = root
        files = []
        for current, dirs, names in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d not in _EXCLUDED and
                             (include_hidden or not d.startswith(".")))
            files.extend(Path(current) / name for name in sorted(names)
                         if include_hidden or not name.startswith("."))
    for path in files:
        try:
            relative = path.relative_to(base).as_posix()
            if filename_pattern and not (fnmatch.fnmatch(path.name, filename_pattern) or
                                          fnmatch.fnmatch(relative, filename_pattern)):
                continue
            if not query:
                results.append({"path": str(path), "line": None, "text": None})
            else:
                with path.open("r", encoding="utf-8", errors="strict") as stream:
                    for number, line in enumerate(stream, start=1):
                        haystack = line.casefold() if ignore_case else line
                        if needle in haystack:
                            results.append({"path": str(path), "line": number,
                                            "text": line.rstrip("\r\n")[:2000]})
                            if len(results) >= cap:
                                return results
        except (OSError, UnicodeError):
            continue
        if len(results) >= cap:
            break
    return results


def _rg(root: Path, query: str, filename_pattern: str, ignore_case: bool,
        include_hidden: bool, cap: int) -> list[dict]:
    rg = shutil.which("rg")
    if not rg:
        return _fallback(root, query, filename_pattern, ignore_case, include_hidden, cap)
    common = [rg, "--color", "never", "--no-messages"]
    if include_hidden:
        common.append("--hidden")
    for directory in _EXCLUDED:
        common.extend(("--glob", f"!{directory}/**"))
    if filename_pattern:
        command = common + ["--files", "--glob", filename_pattern, str(root)]
        try:
            done = subprocess.run(command, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=30, shell=False)
        except (OSError, subprocess.TimeoutExpired):
            return _fallback(root, query, filename_pattern, ignore_case, include_hidden, cap)
        if done.returncode not in (0, 1):
            _LOG.warning("ripgrep filename search failed for %s: %s", root, done.stderr[:1000])
            return _fallback(root, query, filename_pattern, ignore_case, include_hidden, cap)
        return [{"path": line, "line": None, "text": None}
                for line in done.stdout.splitlines()[:cap]]
    if not query:
        raise ValueError("provide query or filename_pattern")
    command = common + ["--json", "--line-number"]
    if ignore_case:
        command.append("--ignore-case")
    command += ["--", query, str(root)]
    results = []
    try:
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, encoding="utf-8", errors="replace", shell=False) as process:
            for raw in process.stdout:
                try:
                    item = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if item.get("type") != "match":
                    continue
                data = item.get("data", {})
                submatch = data.get("lines", {}).get("text", "")
                results.append({"path": data.get("path", {}).get("text", str(root)),
                                "line": data.get("line_number"),
                                "text": submatch.rstrip("\r\n")[:2000]})
                if len(results) >= cap:
                    process.terminate()
                    break
            process.wait(timeout=3)
            stderr = process.stderr.read() if process.stderr else ""
            if process.returncode not in (0, 1):
                _LOG.warning("ripgrep content search failed for %s: %s", root, stderr[:1000])
                return _fallback(root, query, filename_pattern, ignore_case,
                                 include_hidden, cap)
    except (OSError, subprocess.TimeoutExpired):
        return _fallback(root, query, filename_pattern, ignore_case, include_hidden, cap)
    return results


def search_scale(parameters: dict, **_context) -> str:
    p = parameters or {}
    try:
        roots = _roots(p.get("roots", p.get("root", "")))
        query = str(p.get("query", ""))
        filename_pattern = str(p.get("filename_pattern", ""))
        if not query and not filename_pattern:
            raise ValueError("provide query or filename_pattern")
        page_size = int(p.get("page_size", 50))
        cursor = int(p.get("cursor", 0))
        if not 1 <= page_size <= 200 or cursor < 0 or cursor > _MAX_HITS:
            raise ValueError("page_size must be 1–200 and cursor 0–10,000")
        cap = min(_MAX_HITS + 1, cursor + page_size + 1)
        per_root = max(1, (cap + len(roots) - 1) // len(roots))
        with ThreadPoolExecutor(max_workers=min(4, len(roots))) as pool:
            groups = list(pool.map(lambda root: _rg(
                root, query, filename_pattern, not bool(p.get("case_sensitive", False)),
                bool(p.get("include_hidden", False)), per_root), roots))
        results = sorted((row for group in groups for row in group),
                         key=lambda row: (row["path"].casefold(), row["line"] or 0))[:_MAX_HITS + 1]
        page = results[cursor:cursor + page_size]
        more = len(results) > cursor + page_size
        formatted = " ; ".join(
            f"{row['path']}" + (f":{row['line']}" if row["line"] is not None else "") +
            (f" | {row['text']}" if row["text"] is not None else "") for row in page)
        return outcome.done("search_scale", results=outcome.untrusted(
            "local-search-results", formatted or "No matches."),
            count=len(page), cursor=cursor, next_cursor=cursor + page_size if more else None,
            truncated=len(results) > _MAX_HITS)
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as exc:
        return outcome.failed("search_scale", str(exc))


TOOL = {
    "name": "search_scale",
    "description": "Search local files by filename glob and/or text content. Concurrent roots, paginated results using cursor/page_size, ripgrep acceleration when available and Python fallback otherwise.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "roots": {"type": "ARRAY", "items": {"type": "STRING"}},
            "root": {"type": "STRING"},
            "query": {"type": "STRING"},
            "filename_pattern": {"type": "STRING"},
            "page_size": {"type": "INTEGER"},
            "cursor": {"type": "INTEGER"},
            "case_sensitive": {"type": "BOOLEAN"},
            "include_hidden": {"type": "BOOLEAN"},
        },
    },
    "handler": search_scale,
    "tier": "core",
    "brief": "Concurrent paginated file and content search.",
}
