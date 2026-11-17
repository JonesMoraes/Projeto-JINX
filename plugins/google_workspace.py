"""Google Workspace tools; OAuth can only start from the settings button."""
import copy
import json
import threading
import time
import uuid

from core import confirm, outcome
from core import google_workspace as api

PLUGIN = {"name": "google_workspace",
    "description": "Your configured Google account: gmail_list/read/send (send uses the exact email, subject and body supplied), calendar_list/sync with local agenda, drive_list/create_text. Runs asynchronously; results arrive in panel/voice, status gives last job. Never infer email addresses. OAuth only in settings. Drive is limited to app-created/selected files. Sync is manual, preserves conflicts, omits all-day/recurring events and never automatically deletes remote events.",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["status", "gmail_list", "gmail_read", "gmail_send", "calendar_list", "calendar_sync", "drive_list", "drive_create_text"]},
        **{k: {"type": "STRING"} for k in ("id", "query", "to", "subject", "body", "name", "text")},
        "limit": {"type": "INTEGER", "description": "1–10, default 5"}}, "required": ["action"]}}

PLUGIN_SETTINGS = {"namespace": "google_workspace", "title": "GOOGLE — CONECTAR SUA CONTA / CONNECT YOUR ACCOUNT",
    "fields": [
        {"key": "client_file", "label": "JSON OAuth Desktop dentro de config/ / Desktop OAuth JSON in config/", "type": "text", "default": "google_client_secret.json"},
        {"key": "gmail_read", "label": "Ler Gmail / Read Gmail", "type": "toggle", "default": False},
        {"key": "gmail_send", "label": "Enviar Gmail (inclui leitura para verificar) / Send Gmail (includes read verification)", "type": "toggle", "default": False},
        {"key": "calendar", "label": "Ler/alterar eventos Calendar / Read/write Calendar events", "type": "toggle", "default": False},
        {"key": "calendar_id", "label": "ID Calendar (vazio: primary) / Calendar ID", "type": "text"},
        {"key": "calendar_sync", "label": "Permitir sync manual da agenda / Allow manual agenda sync", "type": "toggle", "default": False},
        {"key": "drive", "label": "Drive: arquivos deste app / Drive: this app's files", "type": "toggle", "default": False},
        {"key": "youtube", "label": "Upload YouTube + leitura para verificar / YouTube upload + verification", "type": "toggle", "default": False}],
    "action": {"label": "ENTRAR COM GOOGLE (YOUTUBE EM ETAPA SEPARADA)", "run": api.connect}}

_lock = threading.RLock()
_job = None


def _notify(player, method, *args):
    fn = getattr(player, method, None)
    if callable(fn):
        try:
            fn(*args)
        except Exception:
            pass  # Closing the panel must never replay a remote write.


def _set(job_id, **values):
    with _lock:
        if _job and _job["id"] == job_id:
            _job.update(values)


def _complete(job_id, result, player, verified=True):
    _set(job_id, state="done" if verified else "unverified", result=result)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    _notify(player, "show_content", "Google Workspace", text[:3900] + ("\n[Resultado abreviado / Result abbreviated]" if len(text) > 3900 else ""))
    _notify(player, "write_log", "SYS: Google — " + ("done" if verified else "unverified"))
    _notify(player, "request_say", "[GOOGLE RESULT] Report briefly in the user's language. No tools. Details are in the panel. " +
            ("Verified API result.\n" if verified else "Partial/unverified result; do not claim completion.\n") +
            outcome.untrusted("google-result", text[:2500]))


def _error(job_id, exc, player):
    reason = str(exc) if isinstance(exc, api.GoogleError) else "Integração não verificada / Integration unverified"
    _complete(job_id, {"error": reason}, player, False)


def _work(job_id, parameters, player):
    try:
        action = parameters["action"]
        service = action.split("_", 1)[0]
        client = api.Client(service, write=action == "gmail_send")
        count = parameters.get("limit", 5)
        if action == "gmail_list":
            result = api.gmail_list(client, parameters.get("query"), count)
        elif action == "gmail_read":
            result = api.gmail_read(client, parameters.get("id"))
        elif action == "gmail_send":
            draft, preview = api.mail_draft(parameters)
            if confirm.pending_title():
                raise api.GoogleError("Há outra confirmação pendente / Another confirmation is pending")
            _notify(player, "show_content", "Revisar e-mail / Review email", preview)
            title = "Enviar e-mail / Send email " + job_id
            def send():
                _set(job_id, state="running")
                try:
                    result = api.gmail_send(client, draft)  # The client checks account identity again.
                    _complete(job_id, result, player)
                    return outcome.done("gmail_send", id=result["message_id"])
                except Exception as exc:
                    _error(job_id, exc, player)
                    return outcome.unverified("gmail_send", "Confira Enviados antes de repetir / Check Sent before retry")
            _set(job_id, state="starting_send", confirmation_title=title, confirmation_at=time.monotonic())
            response = confirm.request("google-mail-" + job_id, title, preview[:300], send)
            with _lock:
                if _job and _job["id"] == job_id and _job["state"] == "starting_send":
                    _job["state"] = "running"
            _notify(player, "request_say", response)
            return
        elif action == "calendar_list":
            count = api.limit(count)
            from datetime import datetime, timezone
            page = client.request("GET", api.calendar_path(api.config().get("calendar_id")), params={
                "timeMin": datetime.now(timezone.utc).isoformat(), "maxResults": count,
                "singleEvents": True, "orderBy": "startTime"})
            if page is None:
                raise api.GoogleError("Calendário não encontrado / Calendar not found")
            result = {"events": [{k: row[k] for k in ("id", "summary", "start", "end", "status") if k in row}
                                 for row in page.get("items", [])], "has_more": bool(page.get("nextPageToken"))}
        elif action == "calendar_sync":
            if api.config().get("calendar_sync") is not True:
                raise api.GoogleError("Ative sync manual no cartão GOOGLE / Enable manual sync in GOOGLE settings")
            from core.google_calendar_sync import sync
            result = sync(client, api.config().get("calendar_id") or "primary")
        elif action == "drive_list":
            result = api.drive_files(client, count)
        elif action == "drive_create_text":
            result = api.drive_create_text(client, parameters.get("name"), parameters.get("text"))
        else:
            raise api.GoogleError("Ação desconhecida / Unknown action")
        _complete(job_id, result, player, result.get("complete", True))
    except Exception as exc:
        _error(job_id, exc, player)


def run(parameters, player=None, session_memory=None):
    global _job
    try:
        parameters = copy.deepcopy(parameters or {})
        action = parameters.get("action", "status")
        with _lock:
            if action == "status":
                if not _job:
                    return outcome.done("google_status", state="idle")
                data = {k: v for k, v in _job.items() if k != "confirmation_at"}
                return outcome.done("google_status", data=outcome.untrusted("google-status", json.dumps(data, ensure_ascii=False)[:3500]))
            if action not in PLUGIN["parameters"]["properties"]["action"]["enum"]:
                raise ValueError()
            if _job and _job["state"] in ("running", "starting_send"):
                return outcome.unverified("google_workspace", "Operação em andamento; consulte status / Operation in progress; check status", job_id=_job["id"])
            job_id = uuid.uuid4().hex[:10]
            _job = {"id": job_id, "action": action, "state": "running"}
            parameters["action"] = action
            threading.Thread(target=_work, args=(job_id, parameters, player), daemon=True, name="google-workspace").start()
        return outcome.started("google_workspace", job_id=job_id, detail="Resultado no painel/voz; status disponível / Result in panel/voice; status available")
    except Exception:
        return outcome.failed("google_workspace", "Parâmetros inválidos / Invalid parameters")
