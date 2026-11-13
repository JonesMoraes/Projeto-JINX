import json
from core import meeting, outcome


def install(values):
    from core.optional_packages import install as packages
    return packages("meeting")


PLUGIN = {"name": "meeting_assistant", "description": "Explicit meeting start/stop/status. Start records microphone AND system loopback (all computer playback) with visible stop indicator, max 30 min; then configured local Whisper/Groq STT and model summary/action items. Groq sends audio to YOUR configured account. Never start without the user's explicit request.",
    "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING", "enum": ["start", "stop", "status"]}}, "required": ["action"]}}
PLUGIN_SETTINGS = {"namespace": "meeting_assistant", "title": "REUNIÕES / MEETINGS", "fields": [],
    "action": {"label": "INSTALAR CAPTURA OPCIONAL / INSTALL OPTIONAL CAPTURE", "run": install}}


def run(parameters, player=None, session_memory=None):
    try:
        action = (parameters or {}).get("action", "status")
        if action == "start": status = meeting.manager.start(player)
        elif action == "stop": status = meeting.manager.stop()
        elif action == "status": status = meeting.manager.status()
        else: raise ValueError("action")
        if status["state"] == "failed": return outcome.failed("meeting", status["error"])
        if status["state"] in ("starting", "stopping", "transcribing", "partial"):
            return outcome.unverified("meeting", "Captura/processamento pendente ou parcial; consulte status / Capture/processing pending or partial; check status", data=json.dumps(status))
        return outcome.done("meeting_status", data=json.dumps(status), note="Groq envia áudio à sua conta; gravação só enquanto o indicador estiver visível / Groq sends audio to your account; recording indicated visually")
    except Exception as exc:
        return outcome.failed("meeting", str(exc)[:300])
