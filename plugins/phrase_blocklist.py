"""Exact blocked phrase preference port, João Gabriel, CC BY-NC 4.0."""
import json
from core import outcome, session_preferences as prefs

PLUGIN = {"name": "phrase_blocklist", "description": "Add/remove/list exact phrases to ignore. Local STT and typed commands are filtered before model; native Gemini Live audio is advisory only, not guaranteed.",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["add", "remove", "list"]}, "phrase": {"type": "STRING"}}, "required": ["action"]}}
PLUGIN_SETTINGS = {"namespace": "phrase_blocklist", "title": "FRASES IGNORADAS / IGNORED PHRASES — LIVE: ORIENTATIVO / ADVISORY",
    "fields": [{"key": "phrases", "label": "Frases exatas separadas por ; / Exact phrases separated by ;", "type": "text"}]}


def run(parameters, player=None, session_memory=None):
    try:
        p = parameters or {}
        action = p.get("action", "list")
        if action not in ("add", "remove", "list"):
            raise ValueError("action")
        if action != "list":
            prefs.edit_phrase(action, p.get("phrase"))
        return outcome.done("phrase_blocklist", phrases=outcome.untrusted("blocked-phrase-data", json.dumps(prefs.phrases(), ensure_ascii=False)),
                            limitation="Gemini Live: orientação apenas / advisory only", guidance=prefs.guidance())
    except Exception:
        return outcome.failed("phrase_blocklist", "Frase inválida ou falha ao salvar / Invalid phrase or save failure")
