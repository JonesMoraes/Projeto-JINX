"""Humor switch adapted from João Gabriel, CC BY-NC 4.0; see NOTICE.md."""
from core import outcome, session_preferences as prefs

PLUGIN = {"name": "humor_mode", "description": "Humor on/off/status. Brief friendly dry humor; serious topics stay serious and focus has priority.",
    "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING", "enum": ["on", "off", "status"]}}, "required": ["action"]}}
PLUGIN_SETTINGS = {"namespace": "humor", "title": "MODO HUMOR / HUMOR MODE", "fields": [
    {"key": "enabled", "label": "Humor ativo / Humor enabled", "type": "toggle", "default": False}]}


def run(parameters, player=None, session_memory=None):
    try:
        action = (parameters or {}).get("action", "status")
        if action not in ("on", "off", "status"):
            raise ValueError("action")
        if action != "status":
            prefs.save("humor", {"enabled": action == "on"})
        return outcome.done("humor_mode", enabled=prefs.enabled("humor"), guidance=prefs.guidance())
    except Exception:
        return outcome.failed("humor_mode", "Não foi possível aplicar o humor / Could not apply humor")
