"""Explicit camera based posture and push-up feedback."""
from core import pose_monitor, outcome
from core.optional_packages import install


def install_fitness(_values):
    return install("fitness")


PLUGIN = {"name": "fitness_monitor",
    "description": "After an explicit start request, use the visible camera to give simple posture reminders or count push-ups locally. No recording, upload or medical diagnosis. Requires optional MediaPipe; stop ends capture.",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["posture", "pushups", "stop", "status"]}}, "required": ["action"]}}
PLUGIN_SETTINGS = {"namespace": "fitness_monitor", "title": "VISÃO E POSTURA / VISION & POSTURE",
                   "fields": [], "action": {"label": "INSTALAR MODELO OPCIONAL / INSTALL OPTIONAL MODEL",
                                               "run": install_fitness}}


def run(parameters, player=None, session_memory=None):
    action = (parameters or {}).get("action", "status")
    if action == "status": return outcome.done("fitness", data=str(pose_monitor.status()))
    if action == "stop":
        pose_monitor.stop()
        if player and callable(getattr(player, "stop_camera_stream", None)):
            player.stop_camera_stream()
        return outcome.done("fitness", state="off")
    if action not in ("posture", "pushups"):
        return outcome.failed("fitness", "Unknown activity")
    if player is None or not callable(getattr(player, "start_camera_stream", None)):
        return outcome.failed("fitness", "Open the desktop HUD to enable camera analysis")
    state = pose_monitor.start(action, lambda msg: player.write_log("SYS: " + msg))
    if not pose_monitor.status()["active"]: return outcome.failed("fitness", state)
    player.show_content("Monitoramento de movimento", "Câmera visível; análise local a baixa frequência. Sem gravação, envio ou diagnóstico. Diga ‘pare’ para encerrar.")
    try: player.start_camera_stream()
    except Exception:
        pose_monitor.stop()
        return outcome.failed("fitness", "Could not start camera stream")
    return outcome.done("fitness", note=state)
