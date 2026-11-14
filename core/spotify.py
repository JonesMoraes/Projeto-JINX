"""Spotify desktop PKCE and bounded REST calls, using requests already installed."""
import base64
import hashlib
import json
import os
import re
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

from memory.config_manager import CONFIG_DIR, get_plugin_config

SCOPES = {"read": {"user-read-playback-state"},
          "playlists": {"playlist-read-private", "playlist-read-collaborative"},
          "control": {"user-modify-playback-state", "user-read-playback-state"}}
TOKEN_NAME = "spotify_token.json"
_auth_lock = threading.RLock()


class SpotifyError(RuntimeError):
    """Only fixed, user-safe messages may cross the tool boundary."""


def config():
    return get_plugin_config("spotify")


def selected_scopes(cfg):
    return sorted(set().union(*(v for k, v in SCOPES.items() if cfg.get(k) is True)))


def client_id(cfg):
    value = str(cfg.get("client_id") or "").strip()
    if not re.fullmatch(r"[a-fA-F0-9]{32}", value):
        raise SpotifyError("Informe seu Client ID no cartão SPOTIFY / Enter your Client ID in SPOTIFY settings")
    return value


def _path():
    root = Path(CONFIG_DIR).resolve()
    path = root / TOKEN_NAME
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise SpotifyError("Destino do token inválido / Invalid token destination")
    return path


def _save(data):
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    if temporary.is_symlink():
        raise SpotifyError("Destino temporário inválido / Invalid temporary destination")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(data, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _read():
    try:
        path = _path()
        if path.stat().st_size > 65536:
            raise ValueError()
        token = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(token, dict) or not token.get("access_token") or not token.get("connection"):
            raise ValueError()
        return token
    except Exception:
        raise SpotifyError("Conecte sua conta no cartão SPOTIFY / Connect your account in SPOTIFY settings") from None


def _token_request(data):
    import requests
    try:
        with requests.post("https://accounts.spotify.com/api/token", data=data,
                           timeout=(4, 12), allow_redirects=False) as response:
            if response.status_code != 200:
                raise ValueError()
            result = response.json()
            if (not isinstance(result, dict) or not isinstance(result.get("access_token"), str)
                    or not result["access_token"] or str(result.get("token_type", "")).lower() != "bearer"
                    or not 0 < int(result.get("expires_in", 0)) <= 86400):
                raise ValueError()
            return result
    except Exception:
        raise SpotifyError("Sessão Spotify indisponível; reconecte / Spotify session unavailable; reconnect") from None


def _callback(path, state):
    """Invalid requests cannot terminate or authorize the listener."""
    if len(path) > 8192:
        return None
    parsed = urlsplit(path)
    query = parse_qs(parsed.query)
    if parsed.path != "/callback" or query.get("state") != [state]:
        return None
    if "error" in query:
        return {"denied": True}
    code = query.get("code", [])
    return {"code": code[0]} if len(code) == 1 and 0 < len(code[0]) <= 4096 else None


def _authorize(cid, scopes):
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(32)
    result = {}

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            self.request.settimeout(2)
            super().setup()

        def log_message(self, *_):
            pass  # Authorization codes must never appear in HTTP access logs.

        def do_GET(self):
            received = _callback(self.path, state)
            if received:
                result.update(received)
            self.send_response(200 if received else 400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"JINX: pode fechar esta aba / You may close this tab." if received else b"Invalid callback")

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        server.timeout = 1
        redirect = f"http://127.0.0.1:{server.server_port}/callback"
        url = "https://accounts.spotify.com/authorize?" + urlencode({
            "client_id": cid, "response_type": "code", "redirect_uri": redirect,
            "scope": " ".join(scopes), "state": state, "code_challenge_method": "S256",
            "code_challenge": challenge})
        if not webbrowser.open(url):
            raise SpotifyError("Não foi possível abrir o navegador / Could not open browser")
        deadline = time.monotonic() + 180
        while not result and time.monotonic() < deadline:
            server.handle_request()
    if not result.get("code"):
        raise SpotifyError("Consentimento cancelado ou expirado / Consent cancelled or expired")
    return _token_request({"grant_type": "authorization_code", "client_id": cid,
                           "code": result["code"], "code_verifier": verifier, "redirect_uri": redirect})


def connect(values):
    """UI settings callback only; the voice tool never initiates OAuth."""
    if not _auth_lock.acquire(blocking=False):
        return False, "Conexão já em andamento / Connection already in progress"
    try:
        cfg = dict(values or {})
        cid, scopes = client_id(cfg), selected_scopes(cfg)
        if not scopes:
            raise SpotifyError("Selecione as permissões necessárias / Select needed permissions")
        data = _authorize(cid, scopes)
        if not set(scopes).issubset(set(str(data.get("scope", "")).split())) or not data.get("refresh_token"):
            raise SpotifyError("Consentimento incompleto; conexão anterior preservada / Incomplete consent; previous connection preserved")
        current = config()
        if client_id(current) != cid or selected_scopes(current) != scopes:
            raise SpotifyError("Configuração mudou durante o login / Settings changed during login")
        data.update(client_id=cid, expires_at=time.time() + int(data["expires_in"]), connection=secrets.token_hex(16))
        _save(data)
        return True, "Conta Spotify conectada / Spotify account connected"
    except SpotifyError as exc:
        return False, str(exc)
    except Exception:
        return False, "Conexão Spotify não concluída / Spotify connection incomplete"
    finally:
        _auth_lock.release()


def _credentials(permission, expected=None):
    with _auth_lock:
        cfg = config()
        needed = SCOPES[permission]
        if cfg.get(permission) is not True:
            raise SpotifyError("Permissão desligada no cartão SPOTIFY / Permission disabled in SPOTIFY settings")
        data = _read()
        signature = (client_id(cfg), data["connection"], tuple(selected_scopes(cfg)))
        if data.get("client_id") != signature[0] or (expected is not None and expected != signature):
            raise SpotifyError("Conta/configuração mudou; solicite novamente / Account or settings changed; request again")
        if not needed.issubset(set(str(data.get("scope", "")).split())):
            raise SpotifyError("Permissão ausente; reconecte / Missing permission; reconnect")
        if float(data.get("expires_at", 0)) <= time.time() + 30:
            if not data.get("refresh_token"):
                raise SpotifyError("Sessão expirada; reconecte / Session expired; reconnect")
            fresh = _token_request({"grant_type": "refresh_token", "refresh_token": data["refresh_token"],
                                    "client_id": signature[0]})
            fresh.setdefault("scope", data["scope"])
            fresh.setdefault("refresh_token", data["refresh_token"])
            if not needed.issubset(set(str(fresh["scope"]).split())):
                raise SpotifyError("Permissão renovada incompleta; reconecte / Refreshed permission incomplete; reconnect")
            data.update(fresh, expires_at=time.time() + int(fresh["expires_in"]))
            _save(data)
        return data["access_token"], signature


class Client:
    def __init__(self, permission):
        self.permission = permission
        _, self.signature = _credentials(permission)

    def request(self, method, path, *, params=None, body=None):
        import requests
        allowed = {("GET", "/me/player"), ("GET", "/me/player/devices"), ("GET", "/me/playlists"),
                   ("PUT", "/me/player/play"), ("PUT", "/me/player/pause"), ("PUT", "/me/player"),
                   ("POST", "/me/player/next"), ("POST", "/me/player/previous")}
        if (method, path) not in allowed:
            raise SpotifyError("Operação Spotify inválida / Invalid Spotify operation")
        token, _ = _credentials(self.permission, self.signature)
        try:
            with requests.request(method, "https://api.spotify.com/v1" + path,
                    headers={"Authorization": "Bearer " + token}, params=params, json=body,
                    timeout=(4, 12), allow_redirects=False) as response:
                code = response.status_code
                if code == 204:
                    return None
                if code == 403:
                    raise SpotifyError("Spotify recusou: confira Premium, permissões e allowlist do app / Spotify denied: check Premium, permissions and app allowlist")
                if code == 429:
                    raise SpotifyError("Limite Spotify atingido; aguarde antes de repetir / Spotify rate limit; wait before retrying")
                if code == 404:
                    raise SpotifyError("Abra o Spotify e selecione um dispositivo / Open Spotify and select a device")
                if code != 200:
                    raise SpotifyError(f"Spotify HTTP {code}; reconecte ou tente depois / Reconnect or retry later")
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError()
                return data
        except SpotifyError:
            raise
        except Exception:
            raise SpotifyError("Resposta não verificada; confira Spotify antes de repetir / Unverified response; check Spotify before retrying") from None


def playback(client):
    data = client.request("GET", "/me/player")
    if data is None:
        return {"available": False}
    item, device, context = data.get("item") or {}, data.get("device") or {}, data.get("context") or {}
    return {"available": True, "is_playing": data.get("is_playing"), "device_id": device.get("id"),
            "track_uri": item.get("uri"), "track": str(item.get("name") or "")[:200],
            "context_uri": context.get("uri")}


def devices(client):
    data = client.request("GET", "/me/player/devices")
    if not isinstance(data, dict) or not isinstance(data.get("devices"), list):
        raise SpotifyError("Lista de dispositivos indisponível / Device list unavailable")
    return [{k: row.get(k) for k in ("id", "name", "type", "is_active", "is_restricted")}
            for row in data["devices"][:100] if isinstance(row, dict)]


def playlists(client, count=5, offset=0):
    if type(count) is not int or not 1 <= count <= 20 or type(offset) is not int or not 0 <= offset <= 10000:
        raise SpotifyError("Limite 1–20; offset 0–10000 / Limit 1–20; offset 0–10000")
    data = client.request("GET", "/me/playlists", params={"limit": count, "offset": offset})
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise SpotifyError("Lista de playlists indisponível / Playlist list unavailable")
    return {"items": [{"id": row.get("id"), "name": str(row.get("name") or "")[:200], "uri": row.get("uri")}
                      for row in data["items"][:count] if isinstance(row, dict)],
            "has_more": bool(data.get("next")), "next_offset": offset + count if data.get("next") else None}


def control(client, action, device_id=None, playlist_uri=None):
    if action not in ("play", "pause", "next", "previous", "transfer"):
        raise SpotifyError("Controle inválido / Invalid control")
    if playlist_uri and (action != "play" or not re.fullmatch(r"spotify:playlist:[A-Za-z0-9]{22}", str(playlist_uri))):
        raise SpotifyError("Use o URI exato da playlist / Use the exact playlist URI")
    rows = devices(client)
    if device_id:
        matches = [d for d in rows if d["id"] == device_id]
    else:
        matches = [d for d in rows if d.get("is_active") is True]
    if len(matches) != 1 or not matches[0].get("id") or matches[0].get("is_restricted") is not False:
        raise SpotifyError("Selecione ID de dispositivo disponível e não restrito / Select an available unrestricted device ID")
    target = matches[0]["id"]
    before = playback(client)
    if action == "transfer":
        if not device_id:
            raise SpotifyError("Informe ID do dispositivo de destino / Provide target device ID")
        client.request("PUT", "/me/player", body={"device_ids": [target], "play": False})
    else:
        method = "POST" if action in ("next", "previous") else "PUT"
        client.request(method, "/me/player/" + action, params={"device_id": target},
                       body={"context_uri": playlist_uri} if playlist_uri else None)
    after = playback(client)
    verified = after.get("available") is True and after.get("device_id") == target
    if action in ("play", "pause"):
        verified = verified and after.get("is_playing") is (action == "play")
        if playlist_uri:
            verified = verified and after.get("context_uri") == playlist_uri
    elif action in ("next", "previous"):
        # A different observed track is evidence; the same track isn't failure.
        verified = verified and bool(before.get("track_uri")) and bool(after.get("track_uri")) and before["track_uri"] != after["track_uri"]
    return {"action": action, "verified": bool(verified), "playback": after}


def media_key(action):
    # Explicit fallback only: global keys can affect a different application.
    from actions import computer_settings
    handlers = {"toggle": computer_settings.media_play_pause, "next": computer_settings.media_next,
                "previous": computer_settings.media_previous, "stop": computer_settings.media_stop}
    if action not in handlers:
        raise SpotifyError("Tecla inválida; use toggle/next/previous/stop / Invalid media key")
    handlers[action]()
    return {"verified": False, "note": "Tecla global enviada; pode controlar outro app / Global key sent; may control another app"}
