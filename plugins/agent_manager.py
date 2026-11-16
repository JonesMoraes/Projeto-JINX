"""User-facing multi-agent controls.

The plugin is intentionally narrow: it switches profiles, keeps isolated
in-memory histories, and offers a bounded tool-free debate. It never executes
Markdown instructions or delegates tools during a debate.
"""
from __future__ import annotations

from pathlib import Path

PLUGIN = {
    "name": "agent_manager",
    "description": "List, switch, reset, and mediate conversations between selectable AI agents.",
    "behavior": "BLOCKING",
    "tier": "normal",
    "brief": "Use for explicit agent selection or a bounded agent debate.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "list, current, switch, reset, history, or debate"},
            "agent": {"type": "STRING", "description": "Agent name for switch/reset/history"},
            "topic": {"type": "STRING", "description": "Topic for debate"},
            "turns": {"type": "INTEGER", "description": "Debate turns, capped by the manager"},
        },
        "required": ["action"],
    },
}


def _manager():
    from core.multi_agent import get_manager
    return get_manager(Path(__file__).resolve().parent.parent)


def run(parameters, player=None, session_memory=None):
    params = parameters or {}
    action = str(params.get("action") or "").strip().lower()
    manager = _manager()
    if action == "list":
        return "Available agents: " + ", ".join(
            f"{item['name']} ({'active' if item['active'] else 'available'})"
            for item in manager.describe()
        )
    if action == "current":
        profile = manager.current()
        return f"Active agent: {profile.name} — {profile.title}."
    if action in {"switch", "activate"}:
        profile = manager.switch(params.get("agent"))
        # A resumed Live session would mix contexts. Ask main.py to rebuild it
        # without resumption; absent in unit tests and harmless for other callers.
        callback = getattr(player, "request_agent_reconnect", None)
        if callable(callback):
            callback()
        return f"Switched to {profile.title} ({profile.name}). New turns use an isolated session."
    if action == "reset":
        name = manager.reset(params.get("agent"))
        return f"Conversation state reset for {name}."
    if action == "history":
        rows = manager.history(params.get("agent"))
        return "\n".join(rows[-12:]) if rows else "No conversation turns stored for this agent."
    if action in {"debate", "conversation"}:
        result = manager.debate(params.get("topic"), params.get("turns", 4))
        return result or "The mediated conversation produced no answer."
    return "Unknown agent action. Use list, current, switch, reset, history, or debate."
