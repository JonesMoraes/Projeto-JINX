"""Expose the local manifest-based skill library to JINX tool calling."""
from __future__ import annotations

import asyncio
import threading
from pathlib import Path

from core import outcome

PLUGIN = {
    "name": "skill_registry",
    "description": "Lista, resolve e executa skills locais declaradas por SKILL.md. "
                   "Use action=list para descobrir capacidades; action=run para executar "
                   "uma skill pelo nome com parâmetros estruturados.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["list", "resolve", "run"]},
            "name": {"type": "STRING"},
            "intent": {"type": "STRING"},
            "params": {"type": "OBJECT"},
        },
        "required": ["action"],
    },
    "tier": "extra",
    "brief": "Discover or run a local JINX skill.",
}

_LOCK = threading.RLock()
_REGISTRY = None


def _registry():
    global _REGISTRY
    with _LOCK:
        if _REGISTRY is None:
            from adapters.os_adapter import get_backend
            from core.events import EventBus
            from skills import SkillContext, SkillRegistry

            root = Path(__file__).resolve().parent.parent / "skills"
            context = SkillContext(os_backend=get_backend(), event_bus=EventBus())
            _REGISTRY = SkillRegistry(root, context=context, watch=True)
        return _REGISTRY


def run(parameters: dict, player=None, session_memory=None) -> str:
    del player, session_memory
    action = str(parameters.get("action", "list")).strip().lower()
    try:
        registry = _registry()
        if action == "list":
            rows = registry.list_skills()
            if not rows:
                return "No local skills are installed yet. Add a skill folder with SKILL.md and handler.py."
            return "Local skills: " + "; ".join(
                f"{row['name']} v{row['version']}: {row['description']}"
                for row in rows)
        if action == "resolve":
            skill_name = registry.resolve_intent(parameters.get("intent", ""))
            if skill_name:
                return outcome.done("skill_resolve", skill=skill_name)
            return outcome.unverified("skill_resolve", "No unique exact intent match was found.")
        if action != "run":
            return outcome.failed("skill_registry", "Unsupported action.", action=action)
        name = str(parameters.get("name", "")).strip()
        result = asyncio.run(registry.run(name, parameters.get("params") or {}))
        if result.status == "done":
            return outcome.done("skill_run", skill=name, message=result.message,
                                data=dict(result.data))
        if result.status == "unverified":
            return outcome.unverified("skill_run", result.message or "Result was not verified.",
                                      skill=name, data=dict(result.data))
        return outcome.failed("skill_run", result.message or "Skill execution failed.",
                              skill=name, data=dict(result.data))
    except Exception as exc:
        return outcome.failed("skill_registry", str(exc))
