"""Google desktop OAuth and bounded Workspace REST calls; no imports at discovery.

Consent is initiated only by the settings button. Secrets stay under config/;
neither tool parameters nor remote content can select an OAuth endpoint.
"""
import base64
import hashlib
import json
import os
import re
import threading
import uuid
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import quote

from memory.config_manager import CONFIG_DIR, get_plugin_config

SCOPES = {
    "gmail_read": "https://www.googleapis.com/auth/gmail.readonly",
    "gmail_send": "https://www.googleapis.com/auth/gmail.send",
    "calendar": "https://www.googleapis.com/auth/calendar.events",
    "drive": "https://www.googleapis.com/auth/drive.file",
    "youtube": "https://www.googleapis.com/auth/youtube.upload",
    "youtube_read": "https://www.googleapis.com/auth/youtube.readonly",
}
BASES = {"gmail": "https://gmail.googleapis.com/gmail/v1/users/me",
         "calendar": "https://www.googleapis.com/calendar/v3",
         "drive": "https://www.googleapis.com/drive/v3",
         "youtube": "https://www.googleapis.com/youtube/v3"}
TOKEN_NAME = "google_workspace_token.json"
_auth_lock = threading.RLock()


class GoogleError(RuntimeError):
    """A safe user-facing error, never the SDK's token-bearing exception."""


def config():
    return get_plugin_config("google_workspace")


def selected_scopes(cfg):
    keys = [k for k in SCOPES if cfg.get(k) is True]
    if "gmail_send" in keys and "gmail_read" not in keys:
        # Read access is needed to verify SENT after sending.
        keys.append("gmail_read")
    if 'youtube' in keys and 'youtube_read' not in keys:
        keys.append('youtube_read')
    return sorted(SCOPES[k] for k in keys)


def secret_path(name):
    root = Path(CONFIG_DIR).resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or path == root:
        raise GoogleError("Mantenha o arquivo OAuth dentro de config/ / Keep OAuth file inside config/")
    return path


def write_secret(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    # A local symlink must not redirect credentials outside config/.
    if path.is_symlink():
        raise GoogleError("Destino OAuth inválido / Invalid OAuth destination")
    temporary = path.with_name(path.name + ".tmp")
    if temporary.is_symlink():
        raise GoogleError("Destino OAuth temporário inválido / Invalid temporary OAuth destination")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def client_definition(cfg):
    try:
        path = secret_path(str(cfg.get("client_file") or "google_client_secret.json"))
        if path.stat().st_size > 65536:
            raise ValueError()
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        desktop = data["installed"]
        if (not str(desktop["client_id"]).endswith(".apps.googleusercontent.com") or
                desktop.get("auth_uri") not in ("https://accounts.google.com/o/oauth2/auth",
                                                "https://accounts.google.com/o/oauth2/v2/auth") or
                desktop.get("token_uri") != "https://oauth2.googleapis.com/token"):
            raise ValueError()
        return data
    except GoogleError:
        raise
    except Exception:
        raise GoogleError("Coloque seu JSON OAuth Desktop em config/google_client_secret.json / Provide your Desktop OAuth JSON in config/") from None


def _read_token():
    try:
        path = secret_path(TOKEN_NAME)
        if path.stat().st_size > 65536:
            raise ValueError()
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("token_uri") != "https://oauth2.googleapis.com/token":
            raise ValueError()
        return data
    except Exception:
        raise GoogleError("Conecte sua conta pelo botão GOOGLE em configurações / Connect your Google account in settings") from None


def connection_signature(cfg=None):
    cfg = config() if cfg is None else cfg
    token = _read_token()
    desktop = client_definition(cfg)["installed"]
    if token.get("client_id") != desktop["client_id"]:
        raise GoogleError("Cliente OAuth mudou; reconecte a conta / OAuth client changed; reconnect")
    value = [token.get("client_id"), token.get("refresh_token"),
             selected_scopes(cfg), cfg.get("calendar_id") or "primary", cfg.get("calendar_sync") is True]
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def connect(values):
    """Settings callback (already on a worker), never called from a voice tool."""
    if not _auth_lock.acquire(blocking=False):
        return False, "Conexão já em andamento / Connection already in progress"
    try:
        cfg = dict(values or {})
        scopes = selected_scopes(cfg)
        if not scopes:
            return False, "Selecione apenas os serviços desejados / Select the services you need"
        definition = client_definition(cfg)
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_config(definition, scopes=scopes,
                                                   autogenerate_code_verifier=True)
        creds = flow.run_local_server(host="127.0.0.1", port=0, open_browser=True,
            timeout_seconds=180, authorization_prompt_message="Autorize o JINX no navegador / Authorize JINX in your browser",
            success_message="JINX: pode fechar esta aba / You may close this tab.", prompt="consent")
        granted = creds.granted_scopes if creds.granted_scopes is not None else creds.scopes
        if not creds.valid or not creds.refresh_token or not set(scopes).issubset(set(granted or [])):
            raise GoogleError("Consentimento incompleto; conexão anterior preservada / Incomplete consent; previous connection preserved")
        # Ignore a consent result if settings changed while the browser was open.
        current = config()
        if selected_scopes(current) != scopes or client_definition(current) != definition:
            raise GoogleError("Configuração mudou durante o login; tente novamente / Settings changed during login; retry")
        data = json.loads(creds.to_json())
        data["scopes"] = list(granted)
        write_secret(secret_path(TOKEN_NAME), data)
        return True, "Conta conectada; serviços selecionados autorizados / Account connected for selected services"
    except GoogleError as exc:
        return False, str(exc)
    except ImportError:
        return False, "Instale as dependências Google de requirements.txt / Install the Google requirements"
    except Exception:
        return False, "OAuth não concluído; confira APIs, usuário de teste e consentimento / OAuth incomplete; check APIs, test user and consent"
    finally:
        _auth_lock.release()


def credentials(service, write=False):
    with _auth_lock:
        cfg = config()
        needed = ([SCOPES["gmail_read"], SCOPES["gmail_send"]] if service == "gmail" and write else
                  [SCOPES["gmail_read" if service == "gmail" else service]])
        if service == 'youtube':
            needed = [SCOPES['youtube'], SCOPES['youtube_read']]
        if not set(needed).issubset(set(selected_scopes(cfg))):
            raise GoogleError("Serviço desligado; selecione e conecte em GOOGLE / Service disabled; select and connect in GOOGLE")
        info = _read_token()
        signature = connection_signature(cfg)
        if not set(needed).issubset(set(info.get("scopes") or [])):
            raise GoogleError("Permissão ausente; reconecte pelo botão GOOGLE / Missing permission; reconnect in settings")
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_info(info)
        if not creds.valid:
            if not creds.refresh_token:
                raise GoogleError("Sessão expirada; reconecte / Session expired; reconnect")
            from google.auth.transport.requests import Request
            transport = Request()
            try:
                def bounded_request(*args, **kwargs):
                    kwargs["timeout"] = 15
                    return transport(*args, **kwargs)
                creds.refresh(bounded_request)
                refreshed = json.loads(creds.to_json())
                refreshed["scopes"] = info["scopes"]
                write_secret(secret_path(TOKEN_NAME), refreshed)
            except Exception:
                raise GoogleError("Não foi possível renovar a sessão; reconecte / Cannot refresh session; reconnect") from None
            finally:
                transport.session.close()
        return creds, signature


class Client:
    def __init__(self, service, write=False):
        if service not in BASES:
            raise GoogleError("Serviço desconhecido / Unknown service")
        self.service = service
        self.creds, self.signature = credentials(service, write)

    def check_connection(self):
        if connection_signature() != self.signature:
            raise GoogleError("Conta/configuração mudou; solicite novamente / Account or settings changed; request again")

    def request(self, method, path, *, params=None, body=None, etag=None):
        import requests
        self.check_connection()
        if not path.startswith("/") or any(v in path for v in ("..", "?", "#", "\\")):
            raise GoogleError("Caminho de API inválido / Invalid API path")
        headers = {"Authorization": "Bearer " + self.creds.token}
        if etag:
            headers["If-Match"] = etag
        try:
            with requests.request(method, BASES[self.service] + path, headers=headers,
                                  params=params, json=body, timeout=(4, 12), allow_redirects=False) as response:
                if response.status_code in (404, 410):
                    return None
                if response.status_code == 412:
                    raise GoogleError("Conflito remoto; alterações preservadas / Remote conflict; changes preserved")
                if response.status_code == 409:
                    raise GoogleError("ID já existe; verifique o recurso antes de repetir / ID exists; verify before retry")
                if response.status_code >= 300:
                    raise GoogleError(f"Google HTTP {response.status_code}; confira consentimento e cota / Check consent and quota")
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError()
                if response.headers.get("ETag"):
                    data["_http_etag"] = response.headers["ETag"]
                return data
        except GoogleError:
            raise
        except Exception:
            # Network exceptions can include URLs and account data.
            raise GoogleError("Resposta Google indisponível; não repita envios sem verificar / Google response unavailable; verify before retrying writes") from None


def identifier(value):
    value = str(value or "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", value):
        raise GoogleError("ID inválido / Invalid ID")
    return value


def calendar_path(calendar_id):
    value = str(calendar_id or "primary")
    if len(value) > 256 or any(c in value for c in "\r\n/\\?#"):
        raise GoogleError("ID de calendário inválido / Invalid calendar ID")
    return "/calendars/" + quote(value, safe="") + "/events"


def limit(value, maximum=10):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise GoogleError(f"Limite 1–{maximum} / Invalid limit")
    return value


def gmail_list(client, query="", count=5):
    count = limit(count)
    query = str(query or "")
    if len(query) > 300:
        raise GoogleError("Busca muito longa / Query too long")
    page = client.request("GET", "/messages", params={"q": query, "maxResults": count}) or {}
    rows = []
    for row in page.get("messages", [])[:count]:
        data = client.request("GET", "/messages/" + identifier(row["id"]), params={"format": "metadata",
            "metadataHeaders": ["From", "To", "Subject", "Date"]})
        if data:
            headers = {h["name"].lower(): str(h["value"])[:300] for h in data.get("payload", {}).get("headers", [])}
            rows.append({"id": data["id"], "headers": headers, "snippet": str(data.get("snippet") or "")[:500]})
    return {"messages": rows, "has_more": bool(page.get("nextPageToken"))}


def gmail_read(client, message_id):
    data = client.request("GET", "/messages/" + identifier(message_id), params={"format": "full"})
    if not data:
        raise GoogleError("Mensagem ausente / Message absent")
    texts = []
    def visit(part, depth=0):
        if depth > 10 or len(texts) >= 30:
            return
        raw = str(part.get("body", {}).get("data") or "")
        if part.get("mimeType") == "text/plain" and raw:
            if len(raw) > 100000:
                texts.append("[Trecho muito grande / Oversize part]")
            else:
                texts.append(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8", errors="replace"))
        for child in part.get("parts", [])[:30]:
            visit(child, depth + 1)
    visit(data.get("payload", {}))
    text = "\n".join(texts) or str(data.get("snippet") or "")
    return {"id": data["id"], "text": text[:6000], "truncated": len(text) > 6000,
            "note": "Texto simples/excerto; anexos e HTML não executados / Plain text/excerpt; attachments and HTML not executed"}


def mail_draft(parameters):
    recipient = str(parameters.get("to") or "").strip()
    subject = str(parameters.get("subject") or "").strip()
    body = str(parameters.get("body") or "").strip()
    if (not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}", recipient) or
            len(recipient) > 254 or not subject or len(subject) > 160 or any(c in subject for c in "\r\n") or
            not body or len(body) > 2500):
        raise GoogleError("Informe um e-mail exato, assunto até 160 e texto até 2500 caracteres / Exact email, subject <=160, body <=2500 required")
    message = EmailMessage()
    message["To"], message["Subject"] = recipient, subject
    message.set_content(body)
    return {"raw": base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")}, f"Para / To: {recipient}\nAssunto / Subject: {subject}\n\n{body}"


def gmail_send(client, draft):
    sent = client.request("POST", "/messages/send", body=draft)
    if not sent or not sent.get("id"):
        raise GoogleError("Envio sem comprovante; verifique Enviados antes de repetir / No send receipt; check Sent before retry")
    observed = client.request("GET", "/messages/" + identifier(sent["id"]), params={"format": "minimal"})
    if not observed or "SENT" not in observed.get("labelIds", []):
        raise GoogleError("Resposta recebida, envio não confirmado em Enviados / Response received; Sent label not verified")
    return {"message_id": sent["id"], "sent_verified": True}


def drive_files(client, count=10):
    result = client.request("GET", "/files", params={"pageSize": limit(count), "q": "trashed = false",
        "fields": "nextPageToken,files(id,name,mimeType,webViewLink)", "orderBy": "modifiedTime desc"}) or {}
    return {"files": result.get("files", []), "has_more": bool(result.get("nextPageToken")),
            "scope": "Somente arquivos criados/abertos com este app (drive.file) / Only files created/opened with this app"}


def drive_create_text(client, name, text):
    name, text = str(name or "").strip(), str(text or "")
    if not name or len(name) > 150 or not text or len(text) > 50000:
        raise GoogleError("Nome até 150 e texto até 50000 caracteres / Invalid name/text size")
    # The upload endpoint is fixed; never accept a model-supplied upload URL.
    import requests
    client.check_connection()
    try:
        boundary = "jinx_" + uuid.uuid4().hex
        metadata = json.dumps({"name": name, "mimeType": "text/plain"}).encode("utf-8")
        content = text.encode("utf-8")
        payload = (b"--" + boundary.encode() + b"\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n" + metadata +
                   b"\r\n--" + boundary.encode() + b"\r\nContent-Type: text/plain; charset=UTF-8\r\n\r\n" + content +
                   b"\r\n--" + boundary.encode() + b"--\r\n")
        with requests.post("https://www.googleapis.com/upload/drive/v3/files", params={"uploadType": "multipart", "fields": "id,name,webViewLink"},
            headers={"Authorization": "Bearer " + client.creds.token, "Content-Type": "multipart/related; boundary=" + boundary},
            data=payload,
            timeout=(4, 20), allow_redirects=False) as response:
            if response.status_code >= 300:
                raise ValueError()
            result = response.json()
        file_id = identifier(result.get("id"))
        actual = client.request("GET", "/files/" + file_id, params={"fields": "id,name,size,md5Checksum,modifiedTime,trashed,webViewLink"})
        if (not actual or actual.get("name") != name or actual.get("trashed") or
                int(actual.get("size", -1)) != len(content) or actual.get("md5Checksum") != hashlib.md5(content).hexdigest()):
            raise ValueError()
        from core import undo, outcome
        def restore():
            client.check_connection()
            latest = client.request("GET", "/files/" + file_id, params={"fields": "id,md5Checksum,modifiedTime,trashed"})
            if (not latest or latest.get("trashed") or
                    not latest.get("_http_etag") or
                    any(latest.get(k) != actual.get(k) for k in ("md5Checksum", "modifiedTime"))):
                return outcome.failed("google_drive_undo", "Arquivo mudou/ausente; preservado / File changed or absent; preserved")
            client.request("PATCH", "/files/" + file_id, body={"trashed": True}, etag=latest["_http_etag"])
            latest = client.request("GET", "/files/" + file_id, params={"fields": "id,trashed"})
            if latest and latest.get("trashed") is True:
                return outcome.done("google_drive_undo", id=file_id)
            return outcome.unverified("google_drive_undo", "Lixeira não confirmada / Trash not verified")
        undo.push_undo("Drive: " + name, restore)
        return {k: actual[k] for k in ("id", "name", "webViewLink") if k in actual}
    except Exception:
        raise GoogleError("Criação no Drive não verificada; confira antes de repetir / Drive creation unverified; check before retry") from None
