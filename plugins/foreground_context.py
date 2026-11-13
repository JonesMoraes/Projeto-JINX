"""Privacy control for active-window metadata."""
import json
from core import foreground_context as foreground, outcome, session_preferences

PLUGIN = {"name": "foreground_context", "description": "Privacy opt-in active app/window-title context without screenshots; enable/disable/status. Window titles may contain personal data. Disabling stops future capture; previously sent context cannot be recalled.",
    "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING", "enum": ["enable", "disable", "status"]}}, "required": ["action"]}}
PLUGIN_SETTINGS = {"namespace": "foreground_context", "title": "PRIVACIDADE DA JANELA / WINDOW PRIVACY", "fields": [
    {"key": "enabled", "label": "Enviar app e título da janela ao modelo (pode conter dados pessoais) / Send active app and window title to model (may contain personal data)", "type": "toggle", "default": False}]}


def run(parameters, player=None, session_memory=None):
    try:
        action = (parameters or {}).get("action", "status")
        if action not in ("enable", "disable", "status"):
            raise ValueError("action")
        if action != "status":
            session_preferences.save("foreground_context", {"enabled": action == "enable"})
        reading = foreground.capture()
        return outcome.done("foreground_context", enabled=foreground.enabled(),
            data=outcome.untrusted("foreground-window", json.dumps(reading, ensure_ascii=False)),
            note="Desligar impede novas capturas; contexto já enviado não é apagado / Disabling stops future capture; previously sent context is not erased")
    except Exception:
        return outcome.unverified("foreground_context", "Contexto indisponível / Context unavailable")
