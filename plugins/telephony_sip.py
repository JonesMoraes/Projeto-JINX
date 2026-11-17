"""Optional SIP/PBX call management with an explicit, opt-in provider setup."""
import importlib.util
import re
from core import outcome
from memory.config_manager import get_plugin_config

PLUGIN = {
    "name": "telephony_sip",
    "description": (
        "Manage calls on a user-configured SIP PBX/provider: report registration, answer or reject an incoming "
        "call, and request transfer to a supplied SIP destination. This is only a SIP client; the user must "
        "provide a SIP account or local PBX. Audio transcription and AI/TTS auto-answer are not implemented "
        "without a compatible native PJSUA2 runtime and explicit user consent. Never claim a call is connected."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["status", "answer", "reject", "transfer"]},
        "destination": {"type": "STRING", "description": "SIP URI or phone number on the configured provider"},
    }, "required": ["action"]},
}

PLUGIN_SETTINGS = {"namespace": "telephony_sip", "title": "TELEFONIA SIP / SIP TELEPHONY",
    "fields": [
        {"key": "server", "label": "Servidor SIP / SIP server", "type": "text",
         "placeholder": "pbx.exemplo.com:5060"},
        {"key": "username", "label": "Usuário SIP / SIP username", "type": "text"},
        {"key": "password", "label": "Senha SIP / SIP password", "type": "password"},
        {"key": "transport", "label": "Transporte / Transport", "type": "choice",
         "options": ["UDP", "TCP", "TLS"], "default": "TLS"},
        {"key": "extension", "label": "Ramal ou URI / Extension or URI", "type": "text"},
    ]}

_SUPPORTED = "PJSUA2 com streaming de mídia não está disponível neste cliente Python. Configure um PBX SIP; atender com IA e transferências seguem desativados até haver um runtime nativo validado."


def _configuration():
    cfg = get_plugin_config("telephony_sip")
    server = str(cfg.get("server") or "").strip()
    username = str(cfg.get("username") or "").strip()
    if not server or not username:
        raise ValueError("Configure servidor e usuário SIP em ⚙ → Configurações dos plugins → Telefonia SIP.")
    if len(server) > 255 or not re.fullmatch(r"[A-Za-z0-9.-]+(?::\d{1,5})?", server):
        raise ValueError("Servidor SIP inválido; informe host e porta, sem esquema ou parâmetros.")
    return cfg


def _probe(values):
    try:
        _configuration()
    except ValueError as exc:
        return False, str(exc)
    if importlib.util.find_spec("pjsua2") is None:
        return False, _SUPPORTED
    return False, "PJSUA2 foi encontrado, mas este projeto ainda não possui o adapter de mídia SIP validado. Nenhuma chamada será iniciada."


PLUGIN_SETTINGS["action"] = {"label": "VERIFICAR CONFIGURAÇÃO SIP / TEST SIP SETUP", "run": _probe}


def run(parameters, player=None, session_memory=None):
    p = parameters or {}
    action = p.get("action")
    if action not in {"status", "answer", "reject", "transfer"}:
        return outcome.failed("telephony_sip", "Ação SIP inválida.")
    if action == "transfer":
        dest = str(p.get("destination") or "").strip()
        if not re.fullmatch(r"(?:sip:)?[A-Za-z0-9+_.-]+(?:@[A-Za-z0-9.-]+(?::\d{1,5})?)?", dest):
            return outcome.failed("telephony_sip", "Informe um ramal, número ou URI SIP válido.")
    try:
        cfg = _configuration()
    except ValueError as exc:
        return outcome.failed("telephony_sip", str(exc))
    if importlib.util.find_spec("pjsua2") is None:
        return outcome.unverified("telephony_sip", _SUPPORTED, action=action,
                                  provider=cfg["server"])
    return outcome.unverified("telephony_sip", _SUPPORTED, action=action,
                              provider=cfg["server"], native_adapter_available=False)
