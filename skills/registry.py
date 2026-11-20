"""Discover, validate, run, and hot-reload folder-based JINX skills."""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import inspect
import json
import logging
import re
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
try:
    from watchdog.events import FileSystemEventHandler
except ImportError:  # hot reload can be disabled on minimal installations
    class FileSystemEventHandler:
        pass

from skills.base import BaseSkill, SkillContext, SkillResult

_log = logging.getLogger(__name__)
_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_SUPPORTED_OS = {"windows", "macos", "linux", "any"}
_JSON_TYPES = {"object": dict, "array": list, "string": str,
               "integer": int, "number": (int, float), "boolean": bool}


@dataclass(frozen=True, slots=True)
class SkillManifest:
    name: str
    description: str
    intents: tuple[str, ...]
    params: dict[str, Any]
    supported_os: tuple[str, ...]
    version: str
    required_capabilities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SkillRecord:
    manifest: SkillManifest
    path: Path
    handler: BaseSkill
    fingerprint: str


def _read_manifest(path: Path) -> SkillManifest:
    text = (path / "SKILL.md").read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError("SKILL.md must start with YAML front matter")
    try:
        _, raw, _body = text.split("---", 2)
    except ValueError as exc:
        raise ValueError("SKILL.md has an unterminated YAML front matter") from exc
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError("SKILL.md front matter must be a mapping")

    name = str(data.get("name", "")).strip().lower()
    description = str(data.get("description", "")).strip()
    version = str(data.get("version", "")).strip()
    intents = data.get("intents", [])
    params = data.get("params", data.get("parameters", {}))
    supported = data.get("supported_os", ["any"])
    capabilities = data.get("required_capabilities", [])
    if not _NAME.fullmatch(name):
        raise ValueError("name must be a lowercase identifier")
    if not description or not version:
        raise ValueError("description and version are required")
    if not isinstance(intents, list) or not intents or not all(
            isinstance(item, str) and item.strip() for item in intents):
        raise ValueError("intents must be a non-empty list of strings")
    if not isinstance(params, dict) or params.get("type", "object") != "object":
        raise ValueError("params must be a JSON schema for an object")
    if not isinstance(supported, list) or not supported or any(
            str(item).lower() not in _SUPPORTED_OS for item in supported):
        raise ValueError("supported_os must contain windows, macos, linux, or any")
    if not isinstance(capabilities, list) or not all(
            isinstance(item, str) and item.strip() for item in capabilities):
        raise ValueError("required_capabilities must be a list of strings")
    # Fail at registration, not later while serializing a tool declaration.
    json.dumps(params)
    return SkillManifest(name, description, tuple(i.strip() for i in intents),
                         params, tuple(str(i).lower() for i in supported), version,
                         tuple(i.strip() for i in capabilities))


def _validate_params(schema: dict[str, Any], params: Any) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise ValueError("skill parameters must be an object")
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    if not isinstance(properties, dict) or not isinstance(required, list):
        raise ValueError("invalid params JSON schema")
    missing = [key for key in required if key not in params]
    if missing:
        raise ValueError("missing required parameter(s): " + ", ".join(map(str, missing)))
    if schema.get("additionalProperties") is False:
        extra = set(params) - set(properties)
        if extra:
            raise ValueError("unknown parameter(s): " + ", ".join(sorted(extra)))
    for key, value in params.items():
        rule = properties.get(key)
        if not isinstance(rule, dict) or "type" not in rule:
            continue
        expected = _JSON_TYPES.get(str(rule["type"]))
        # bool subclasses int in Python, but JSON Schema treats them separately.
        if expected is None or not isinstance(value, expected) or (
                rule["type"] in {"integer", "number"} and isinstance(value, bool)):
            raise ValueError(f"parameter {key!r} must have type {rule['type']}")
        if "enum" in rule and value not in rule["enum"]:
            raise ValueError(f"parameter {key!r} is not an allowed value")
    return params


class _WatchHandler(FileSystemEventHandler):
    """Tiny adapter kept independent from watchdog's optional base classes."""

    def __init__(self, registry: "SkillRegistry") -> None:
        self.registry = registry

    def on_any_event(self, event) -> None:
        if getattr(event, "is_directory", False):
            return
        path = Path(str(getattr(event, "src_path", "")))
        if path.name in {"SKILL.md", "handler.py"}:
            self.registry._queue_reload(path.parent)


class SkillRegistry:
    """Thread-safe skill index with asynchronous dispatch and optional watching."""

    def __init__(self, root: Path, *, context: SkillContext | None = None,
                 watch: bool = True) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.context = context or SkillContext()
        self._lock = threading.RLock()
        self._records: dict[str, SkillRecord] = {}
        self._errors: dict[str, str] = {}
        self._observer = None
        self._reload_pending: dict[Path, threading.Timer] = {}
        self.reload_all()
        if watch:
            self.start_watching()

    def start_watching(self) -> bool:
        """Watch the local skills folder; return False if watchdog is unavailable."""
        with self._lock:
            if self._observer is not None:
                return True
            try:
                from watchdog.observers import Observer
            except ImportError:
                _log.warning("watchdog is unavailable; skills require manual reload")
                return False
            observer = Observer()
            observer.schedule(_WatchHandler(self), str(self.root), recursive=True)
            observer.start()
            self._observer = observer
            return True

    def stop_watching(self) -> None:
        with self._lock:
            observer, self._observer = self._observer, None
            timers = tuple(self._reload_pending.values())
            self._reload_pending.clear()
        for timer in timers:
            timer.cancel()
        if observer is not None:
            observer.stop()
            observer.join(timeout=3)

    def _queue_reload(self, directory: Path) -> None:
        directory = directory.resolve()
        try:
            directory.relative_to(self.root)
        except ValueError:
            return
        with self._lock:
            previous = self._reload_pending.pop(directory, None)
            if previous:
                previous.cancel()
            timer = threading.Timer(0.15, self._reload_directory, args=(directory,))
            timer.daemon = True
            self._reload_pending[directory] = timer
            timer.start()

    def _reload_directory(self, directory: Path) -> None:
        with self._lock:
            self._reload_pending.pop(directory, None)
        try:
            self.reload_skill(directory)
        except Exception:
            _log.exception("Could not hot-reload skill from %s", directory)

    @staticmethod
    def _fingerprint(directory: Path) -> str:
        digest = hashlib.sha256()
        for name in ("SKILL.md", "handler.py"):
            path = directory / name
            digest.update(name.encode())
            digest.update(path.read_bytes())
        return digest.hexdigest()

    def _load(self, directory: Path) -> SkillRecord:
        directory = directory.resolve()
        directory.relative_to(self.root)
        manifest = _read_manifest(directory)
        handler_path = directory / "handler.py"
        if not handler_path.is_file():
            raise ValueError("handler.py is missing")
        fingerprint = self._fingerprint(directory)
        module_name = "_jinx_skill_" + manifest.name + "_" + fingerprint[:12]
        spec = importlib.util.spec_from_file_location(module_name, handler_path)
        if spec is None or spec.loader is None:
            raise ImportError("could not load handler.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            # Compile the current source directly: timestamp/size based .pyc
            # validation can otherwise serve stale code after a quick edit.
            source = handler_path.read_text(encoding="utf-8")
            exec(compile(source, str(handler_path), "exec"), module.__dict__)
            skill_type = getattr(module, "Skill", None)
            if not inspect.isclass(skill_type) or not issubclass(skill_type, BaseSkill):
                # The documented JINX format (skills/img-to-html and the skill
                # adoption spec) names the class Handler; accept both spellings.
                skill_type = getattr(module, "Handler", None)
            if not inspect.isclass(skill_type) or not issubclass(skill_type, BaseSkill):
                raise TypeError("handler.py must expose class Skill(BaseSkill) or Handler(BaseSkill)")
            skill = skill_type()
        except Exception:
            sys.modules.pop(module_name, None)
            raise
        return SkillRecord(manifest, directory, skill, fingerprint)

    def reload_skill(self, directory: Path) -> bool:
        """Load or replace one skill; malformed edits do not replace a good copy."""
        directory = Path(directory).resolve()
        name = directory.name.lower()
        try:
            record = self._load(directory)
            name = record.manifest.name
            with self._lock:
                previous = self._records.get(name)
                if previous and previous.path != record.path:
                    self._remove_module(record)
                    self._errors[name] = "duplicate skill name"
                    return False
                self._records[name] = record
                self._errors.pop(name, None)
            if previous:
                self._remove_module(previous)
            return True
        except ValueError as exc:
            with self._lock:
                self._errors[name] = str(exc)
            _log.warning("Skill %s was not loaded: %s", name, exc)
            return False
        except Exception as exc:
            with self._lock:
                self._errors[name] = str(exc)
            _log.warning("Skill %s was not loaded: %s", name, exc)
            return False

    @staticmethod
    def _remove_module(record: SkillRecord) -> None:
        prefix = "_jinx_skill_" + record.manifest.name + "_"
        for key in tuple(sys.modules):
            if key.startswith(prefix) and record.fingerprint[:12] in key:
                sys.modules.pop(key, None)

    def reload_all(self) -> dict[str, str]:
        found: dict[str, str] = {}
        for directory in sorted(self.root.iterdir()):
            if directory.is_dir() and (directory / "SKILL.md").is_file():
                if not self.reload_skill(directory):
                    found[directory.name] = self._errors.get(directory.name, "invalid skill")
        return found

    def list_skills(self) -> list[dict[str, Any]]:
        with self._lock:
            return [{"name": record.manifest.name,
                     "description": record.manifest.description,
                     "intents": list(record.manifest.intents),
                     "version": record.manifest.version,
                     "supported_os": list(record.manifest.supported_os),
                     "required_capabilities": list(record.manifest.required_capabilities)}
                    for record in sorted(self._records.values(),
                                         key=lambda row: row.manifest.name)]

    def errors(self) -> dict[str, str]:
        with self._lock:
            return dict(self._errors)

    def resolve_intent(self, intent: str) -> str | None:
        """Resolve an exact normalized manifest intent without guessing."""
        normalized = " ".join(str(intent or "").casefold().split())
        if not normalized:
            return None
        with self._lock:
            matches = [record.manifest.name for record in self._records.values()
                       if any(normalized == " ".join(value.casefold().split())
                              for value in record.manifest.intents)]
        return matches[0] if len(matches) == 1 else None

    async def run(self, name: str, params: dict[str, Any],
                  ctx: SkillContext | None = None) -> SkillResult:
        with self._lock:
            record = self._records.get(str(name))
        if record is None:
            return SkillResult("failed", f"Skill {name!r} is not available.")
        try:
            params = _validate_params(record.manifest.params, params)
            context = ctx or self.context
            backend_name = str(getattr(context.os_backend, "os_name", "")).lower()
            allowed = set(record.manifest.supported_os)
            if backend_name and "any" not in allowed and backend_name not in allowed:
                return SkillResult("failed", "Skill does not support this operating system.")
            required = set(record.manifest.required_capabilities)
            provided = set(context.metadata.get("capabilities", ()))
            provided.update(context.services)
            if required - provided:
                return SkillResult("failed", "Missing capability: " +
                                   ", ".join(sorted(required - provided)))
            result = await record.handler.run(params, context)
            if not isinstance(result, SkillResult):
                return SkillResult("failed", "Skill handler returned an invalid result.")
            return result
        except ValueError as exc:
            return SkillResult("failed", str(exc))
        except Exception as exc:
            _log.exception("Skill %s failed", name)
            return SkillResult("failed", f"Skill failed: {exc}")

    async def close(self) -> None:
        self.stop_watching()
        await asyncio.sleep(0)
