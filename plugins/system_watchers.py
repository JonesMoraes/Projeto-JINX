import json
from core import watchers, outcome, session_preferences

PLUGIN = {"name": "system_watchers", "description": "Configure/list/remove crypto price thresholds (CoinGecko coin ID), public HTTPS uptime and RAM spike watchers. Enable explicitly; alerts respect quiet hours. No trades.",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["add", "remove", "list", "enable", "disable"]},
        "kind": {"type": "STRING", "enum": ["crypto", "website", "ram"]}, "id": {"type": "STRING"},
        "coin": {"type": "STRING"}, "currency": {"type": "STRING"}, "url": {"type": "STRING"},
        "threshold": {"type": "NUMBER"}, "direction": {"type": "STRING", "enum": ["above", "below"]},
        "interval": {"type": "INTEGER", "description": "Seconds 60–86400; default 300"}}, "required": ["action"]}}
PLUGIN_SETTINGS = {"namespace": "system_watchers", "title": "MONITORES / WATCHERS", "fields": [
    {"key": "enabled", "label": "Ativar alertas configurados / Enable configured alerts", "type": "toggle", "default": False}]}


def run(parameters, player=None, session_memory=None):
    try:
        p = parameters or {}
        action = p.get("action", "list")
        if action in ("enable", "disable"):
            session_preferences.save("system_watchers", {"enabled": action == "enable"})
        elif action in ("add", "remove"):
            watchers.change(action, p)
        elif action != "list":
            raise ValueError("action")
        return outcome.done("system_watchers", data=outcome.untrusted("watcher-settings", json.dumps(watchers.entries())),
            note="Ative os alertas explicitamente após configurar / Enable alerts explicitly after configuration")
    except Exception:
        return outcome.failed("system_watchers", "Configuração não verificada; confira ID, URL pública, limites e intervalo >=60 s / Configuration unverified; check ID, public URL, thresholds and interval >=60 s")
