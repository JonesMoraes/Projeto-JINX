"""Focus protocol port from João Gabriel, CC BY-NC 4.0; see NOTICE.md."""
import json
from urllib.parse import urlsplit
from core import outcome, session_preferences as prefs
from memory.config_manager import get_plugin_config

PLUGIN = {"name": "focus_mode", "description": "Focus mode start/stop/status: concise replies, suppress idle check-ins, show today's tasks and optional water reminders. Optional user playlist opens in browser, playback unverified.",
    "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING", "enum": ["start", "stop", "status"]}}, "required": ["action"]}}

PLUGIN_SETTINGS = {"namespace": "focus", "title": "MODO FOCO / FOCUS MODE", "fields": [
    {"key": "enabled", "label": "Foco ativo / Focus enabled", "type": "toggle", "default": False},
    {"key": "water_enabled", "label": "Lembrete de água durante o foco / Water reminder during focus", "type": "toggle", "default": False},
    {"key": "water_minutes", "label": "Intervalo em minutos (5–240) / Interval in minutes", "type": "text", "default": "30"},
    {"key": "playlist_url", "label": "SUA playlist HTTPS opcional / YOUR optional HTTPS playlist", "type": "text"}]}


def run(parameters, player=None, session_memory=None):
    try:
        action = (parameters or {}).get("action", "status")
        if action not in ("start", "stop", "status"):
            raise ValueError("action")
        if action != "status":
            prefs.save("focus", {"enabled": action == "start"})
        active = prefs.enabled("focus")
        result = outcome.done("focus_mode", enabled=active, guidance=prefs.guidance())
        if action == "start":
            from plugins.organizer import run as organizer
            result += "\n" + organizer({"action": "agenda", "filter": "today"})
            url = str(get_plugin_config("focus").get("playlist_url") or "").strip()
            if url:
                parsed = urlsplit(url)
                if parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password:
                    import webbrowser
                    try:
                        webbrowser.open(url)
                    except Exception:
                        pass
                result += "\n" + outcome.unverified("focus_playlist", "Reprodução não confirmada; controle a playlist no navegador / Playback unverified; control playlist in browser")
        if action == "stop":
            result += "\nLembretes de foco desligados; playlist aberta no navegador exige pausa manual / Focus reminders off; browser playlist needs manual pause."
        return result
    except Exception:
        return outcome.failed("focus_mode", "Não foi possível aplicar o foco / Could not apply focus mode")
