"""Explicit local-only face-presence monitor."""
from core import presence, outcome

PLUGIN = {"name": "presence_monitor",
    "description": "With an explicit start request, show the live camera and detect whether someone is present locally. It does not identify people, save frames, or upload images. Stop ends the stream and detection.",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["start", "stop", "status"]}}, "required": ["action"]}}


def run(parameters, player=None, session_memory=None):
    action = (parameters or {}).get("action", "status")
    if action == "status":
        return outcome.done("presence", state="on" if presence.active() else "off")
    if action == "stop":
        presence.stop()
        if player and callable(getattr(player, "stop_camera_stream", None)):
            player.stop_camera_stream()
        return outcome.done("presence", state="off")
    if action != "start": return outcome.failed("presence", "Unknown action")
    if player is None or not callable(getattr(player, "start_camera_stream", None)):
        return outcome.failed("presence", "Open the desktop HUD to enable the camera")
    state = presence.start(lambda msg: player.write_log("SYS: " + msg))
    if not presence.active(): return outcome.failed("presence", state)
    player.show_content("Presença ativa", "A câmera fica visível. Detecção local, sem identidade, gravação ou envio. Diga ‘pare o monitor de presença’ para desligar.")
    try:
        player.start_camera_stream()
    except Exception:
        presence.stop()
        return outcome.failed("presence", "Could not start camera stream")
    return outcome.done("presence", note=state)
