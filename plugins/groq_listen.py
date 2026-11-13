"""Groq hearing status adapted from João Gabriel, CC BY-NC 4.0; see NOTICE.md."""
from core import outcome
from memory.config_manager import get_pipeline, get_provider_config, get_provider_mode

PLUGIN = {"name": "groq_listen_status", "description": "Report configured Groq hearing selection and whether YOUR key is set. Not proof of a live transcription. Choose hearing in Engine & Providers.",
    "parameters": {"type": "OBJECT", "properties": {}}}


def run(parameters, player=None, session_memory=None):
    try:
        hearing = get_pipeline().get("stt", "")
        configured = get_provider_mode() == "pipeline" and hearing in ("groq_stt", "whisper@groq")
        cfg = get_provider_config(hearing) if configured else get_provider_config("groq_stt")
        return outcome.done("groq_listen_status", selected=configured, key_present=bool(cfg.get("api_key")),
                            verification="Configuração consultada; transcrição real não comprovada / Settings checked; real transcription not proven")
    except Exception:
        return outcome.failed("groq_listen_status", "Não foi possível ler a configuração / Could not read settings")
