"""Read-only inventory of capabilities already registered in this JINX run."""
from __future__ import annotations

import platform
from datetime import datetime, timezone
from typing import Any


def build_manifest(*, plugins=None, actions=None, providers=None, support=None) -> dict[str, Any]:
    """Return a JSON-serializable capability snapshot without loading providers.

    Pass the registries created by the application to avoid rediscovery or
    imports. Missing registries are reported as empty rather than guessed.
    """
    plugin_rows = plugins.list_for_ui() if plugins is not None else []
    action_rows = _action_rows(actions)
    provider_rows = _provider_rows(providers)
    support_data = _support_data(support)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "platform": support_data.get("os_name") or platform.system(),
        "system_support": support_data,
        "plugins": _clean_rows(plugin_rows, ("name", "description", "valid", "enabled", "error")),
        "actions": action_rows,
        "providers": provider_rows,
    }


def _action_rows(registry) -> list[dict[str, Any]]:
    if registry is None:
        return []
    records = getattr(registry, "_all_records", None)
    if records is None:
        return [{"name": name, "valid": True} for name in sorted(registry.names())]
    return [{"name": rec.name, "valid": bool(rec.valid),
             "description": rec.description, "error": rec.error or None}
            for rec in records]


def _provider_rows(declarations) -> list[dict[str, Any]]:
    if declarations is None:
        return []
    if isinstance(declarations, dict):
        declarations = declarations.values()
    return [{"id": str(row.get("id", "")), "kind": str(row.get("kind", "")),
             "label": str(row.get("label", "")),
             "available": bool(row.get("_available", True))}
            for row in declarations if isinstance(row, dict)]


def _support_data(support) -> dict[str, Any]:
    if support is None:
        try:
            from core.platform_support import detect
            support = detect()
        except Exception:
            return {"os_name": platform.system(), "available": False,
                    "notes": ["Platform capabilities could not be detected."]}
    fields = ("os_name", "can_control_input", "can_capture_screen", "can_focus_windows")
    data = {name: getattr(support, name) for name in fields if hasattr(support, name)}
    data["notes"] = list(getattr(support, "notes", ()) or ())
    data["available"] = True
    return data


def _clean_rows(rows, fields) -> list[dict[str, Any]]:
    return [{key: row[key] for key in fields if key in row}
            for row in rows if isinstance(row, dict)]
