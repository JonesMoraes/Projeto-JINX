"""Adapted from João Gabriel / jgm-source, CC BY-NC 4.0.

Source commit: 87d9ea2bfd600e189ba849a0653039e8c505c978.
"""
from core import outcome
from core.gemini_accounts import status

PLUGIN = {
    "name": "gemini_accounts_status",
    "description": "Show Gemini account fallback/cooldown status without secrets.",
    "parameters": {"type": "OBJECT", "properties": {
        "language": {"type": "STRING", "enum": ["pt-BR", "en"]}}},
}


def _test(values):
    import requests
    rows = []
    ok = True
    for label in ("secondary_key", "tertiary_key"):
        key = str(values.get(label) or "").strip()
        if not key:
            continue
        try:
            response = requests.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                headers={"x-goog-api-key": key}, params={"pageSize": 1}, timeout=12)
            passed = response.status_code == 200
            rows.append(f"{label}: HTTP {response.status_code}")
            ok = ok and passed
        except Exception:
            ok = False
            rows.append(f"{label}: falha de conexão / connection failed")
    return (ok and bool(rows), "; ".join(rows) if rows else
            "Informe uma chave adicional / Enter a fallback key.")


PLUGIN_SETTINGS = {
    "namespace": "gemini",
    "title": "CONTAS GEMINI / GEMINI ACCOUNTS",
    "fields": [
        {"key": "secondary_key", "label": "Segunda chave / Secondary key", "type": "password"},
        {"key": "tertiary_key", "label": "Terceira chave / Third key", "type": "password"},
    ],
    "action": {"label": "TESTAR CHAVES / TEST KEYS", "run": _test},
}


def run(parameters, player=None, session_memory=None):
    try:
        return outcome.done("gemini_accounts_status", accounts=status(
            str(parameters.get("language", "pt-BR")).startswith("en")))
    except Exception:
        return outcome.failed("gemini_accounts_status", "Status indisponível / Status unavailable")
