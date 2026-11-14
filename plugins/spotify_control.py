"""Spotify integration written for JINX from the public API specification."""
import copy
import json
import threading

from core import outcome
from core import spotify as api

PLUGIN = {"name": "spotify_control",
    "description": "Spotify account playback/devices/playlists. Exact device_id and spotify:playlist URI; do not invent IDs. OAuth only in settings. status is last job, playback queries current music. media_key is an EXPLICIT global-key fallback only when user requests it; can affect another app. Never silently fall back after API failure.",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["status", "playback", "devices", "playlists", "play", "pause", "next", "previous", "transfer", "media_key"]},
        "device_id": {"type": "STRING"}, "playlist_uri": {"type": "STRING"},
        "key": {"type": "STRING", "enum": ["toggle", "next", "previous", "stop"]},
        "limit": {"type": "INTEGER"}, "offset": {"type": "INTEGER"}}, "required": ["action"]}}

PLUGIN_SETTINGS = {"namespace": "spotify", "title": "SPOTIFY — SUA CONTA / YOUR ACCOUNT",
    "fields": [
        {"key": "client_id", "label": "Client ID (sem Client Secret) / Client ID (no Client Secret)", "type": "text"},
        {"key": "read", "label": "Ler reprodução e dispositivos / Read playback and devices", "type": "toggle", "default": False},
        {"key": "playlists", "label": "Ler playlists / Read playlists", "type": "toggle", "default": False},
        {"key": "control", "label": "Controlar reprodução (Premium e permissões do app) / Control playback (Premium and app permissions)", "type": "toggle", "default": False}],
    "action": {"label": "CONECTAR NO NAVEGADOR / CONNECT IN BROWSER", "run": api.connect}}

_lock = threading.RLock()
_job = {"state": "idle"}


def _notify(player, method, *args):
    try:
        fn = getattr(player, method, None)
        if callable(fn):
            fn(*args)
    except Exception:
        pass


def _work(parameters, player):
    global _job
    action = parameters["action"]
    try:
        if action == "media_key":
            result = api.media_key(parameters.get("key"))
        else:
            client = api.Client("playlists" if action == "playlists" else "read" if action in ("devices", "playback") else "control")
            if action == "devices":
                result = {"devices": api.devices(client)}
            elif action == "playlists":
                result = api.playlists(client, parameters.get("limit", 5), parameters.get("offset", 0))
            elif action == "playback":
                result = api.playback(client)
            else:
                result = api.control(client, action, parameters.get("device_id"), parameters.get("playlist_uri"))
        verified = result.get("verified", True)
    except Exception as exc:
        result = {"error": str(exc) if isinstance(exc, api.SpotifyError) else "Spotify indisponível / Spotify unavailable"}
        verified = False
    state = "done" if verified else "unverified"
    text = json.dumps(result, ensure_ascii=False)
    with _lock:
        _job = {"state": state, "action": action, "result": result}
    _notify(player, "show_content", "Spotify", text[:3900])
    _notify(player, "request_say", "[SPOTIFY RESULT] Report briefly in the user's language. No tools. " +
            ("Verified observation. " if verified else "Unverified; do not claim success. ") + outcome.untrusted("spotify", text[:2500]))


def run(parameters, player=None, session_memory=None):
    global _job
    try:
        parameters = copy.deepcopy(parameters or {})
        action = parameters.get("action", "status")
        with _lock:
            if action == "status":
                return outcome.done("spotify_status", data=outcome.untrusted("spotify-status", json.dumps(_job, ensure_ascii=False)[:3500]))
            if action not in PLUGIN["parameters"]["properties"]["action"]["enum"]:
                return outcome.failed("spotify", "Ação inválida / Invalid action")
            if _job["state"] == "running":
                return outcome.unverified("spotify", "Operação em andamento / Operation in progress")
            parameters["action"] = action
            _job = {"state": "running", "action": action}
            try:
                threading.Thread(target=_work, args=(parameters, player), daemon=True, name="spotify-control").start()
            except Exception:
                _job = {"state": "failed"}
                raise
        return outcome.started("spotify", detail="Resultado no painel/voz; consulte status / Result in panel/voice; check status")
    except Exception:
        return outcome.failed("spotify", "Parâmetros inválidos / Invalid parameters")
