"""Explicit, bounded two-way agenda sync, with independent Google shadows.

Trello's dirty/shadow fields are never cleared here. Remote deletion, all-day
events and recurrences stay visible as issues instead of deleting local data.
"""
import copy
import hashlib
import json
import threading
from datetime import datetime, timedelta
from pathlib import Path

from core import agenda_store as store
from core.google_workspace import GoogleError, calendar_path, identifier, write_secret

PATH = Path(__file__).resolve().parent.parent / "memory" / "google_calendar_sync.json"
_sync_lock = threading.Lock()
MAX_LOCAL = 200
MAX_REMOTE = 500


def moment(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise GoogleError("Data/hora requer fuso explícito / Date/time requires explicit timezone")
    return parsed


def snapshot(event, remote=False):
    if remote:
        if event.get("status") == "cancelled" or event.get("recurrence") or event.get("recurringEventId"):
            return None
        raw = (event.get("start") or {}).get("dateTime")
        if not raw:
            return None
        return {"title": str(event.get("summary") or "Sem título / Untitled"),
                "due": moment(raw).astimezone().isoformat()}
    return {"title": str(event["title"]), "due": moment(event["due"]).astimezone().isoformat()}


def remote_events(client, path):
    rows, token, seen = [], None, set()
    while True:
        params = {"maxResults": 100, "showDeleted": True, "singleEvents": False}
        if token:
            params["pageToken"] = token
        page = client.request("GET", path, params=params)
        if not isinstance(page, dict) or not isinstance(page.get("items", []), list):
            raise GoogleError("Calendário não encontrado/resposta incompleta / Calendar absent or incomplete response")
        rows.extend(page.get("items", []))
        token = page.get("nextPageToken")
        if len(rows) > MAX_REMOTE or (token and len(rows) >= MAX_REMOTE) or token in seen:
            raise GoogleError("Calendário muito grande/paginação inválida; sincronização suspensa / Oversize calendar or invalid pagination; sync suspended")
        if not token:
            return rows
        seen.add(token)


def _state(scope):
    if not PATH.exists():
        return {"scope": scope, "links": {}}
    try:
        state = json.loads(PATH.read_text(encoding="utf-8"))
        if state["scope"] != scope:
            raise GoogleError("Conta/calendário mudou; vínculos preservados para revisão / Account or calendar changed; review existing links")
        if not isinstance(state["links"], dict):
            raise ValueError()
        return state
    except GoogleError:
        raise
    except Exception:
        raise GoogleError("Vínculos Google inválidos; arquivo preservado / Invalid Google links; file preserved") from None


def sync(client, calendar_id="primary"):
    if not _sync_lock.acquire(blocking=False):
        raise GoogleError("Sincronização em andamento / Sync already running")
    try:
        path = calendar_path(calendar_id)
        scope = hashlib.sha256((client.signature + "|" + calendar_id).encode()).hexdigest()
        state = _state(scope)
        remote = {identifier(e["id"]): e for e in remote_events(client, path)}
        issues, changes = [], 0
        # This lock coordinates with the existing local CRUD and Trello sync.
        with store.lock:
            events = store.load()
            if len(events) > MAX_LOCAL:
                raise GoogleError("Limite de 200 eventos locais; sincronização suspensa / Local agenda limit; sync suspended")
            linked = set()
            for event in events:
                local_id = event["id"]
                link = state["links"].get(local_id)
                if event.get("archived"):
                    if link:
                        linked.add(link["id"])
                        if remote.get(link["id"], {}).get("status") != "cancelled":
                            issues.append({"id": local_id, "reason": "Arquivo local preservado; remova no Calendar se desejado / Local archive; remove in Calendar if desired"})
                    continue
                local = snapshot(event)
                if link is None:
                    rid = "jin" + hashlib.sha256((scope + local_id).encode()).hexdigest()
                    link = {"id": rid, "creating": True, "shadow": copy.deepcopy(local)}
                    state["links"][local_id] = link
                    write_secret(PATH, state)  # Durable ID before a possibly ambiguous POST.
                rid = link["id"]
                linked.add(rid)
                current = remote.get(rid)
                if link.get("creating"):
                    if current is None:
                        # Check the stable ID before insert (including after a timeout/restart).
                        current = client.request("GET", path + "/" + rid)
                    if current is None:
                        end = (moment(local["due"]) + timedelta(minutes=30)).isoformat()
                        client.request("POST", path, params={"sendUpdates": "none"}, body={"id": rid,
                            "summary": local["title"], "start": {"dateTime": local["due"]}, "end": {"dateTime": end},
                            "extendedProperties": {"private": {"jinxAgenda": local_id}}})
                        current = client.request("GET", path + "/" + rid)
                    marker = ((current or {}).get("extendedProperties") or {}).get("private", {}).get("jinxAgenda")
                    if marker != local_id or snapshot(current, True) != link["shadow"]:
                        issues.append({"id": local_id, "reason": "Criação não confirmada/conflitante / Creation unverified or conflicting"})
                        continue
                    link.pop("creating", None)
                    link["shadow"] = snapshot(current, True)
                    write_secret(PATH, state)
                    remote[rid] = current
                    changes += 1
                if current is None or current.get("status") == "cancelled":
                    issues.append({"id": local_id, "reason": "Remoto ausente/cancelado; local preservado / Remote missing/cancelled; local preserved"})
                    continue
                incoming = snapshot(current, True)
                if incoming is None:
                    issues.append({"id": local_id, "reason": "Dia inteiro/recorrência não sincronizado / All-day or recurrence unsupported"})
                    continue
                previous = link.get("shadow")
                local_changed, remote_changed = local != previous, incoming != previous
                if local_changed and remote_changed and local != incoming:
                    issues.append({"id": local_id, "reason": "Conflito local/remoto; ambas versões preservadas / Local/remote conflict; both preserved"})
                    continue
                if local_changed and local != incoming:
                    # Re-fetch and use a conditional write; never overwrite a racing edit.
                    fresh = client.request("GET", path + "/" + rid)
                    if not fresh or fresh.get("etag") != current.get("etag") or not fresh.get("etag"):
                        issues.append({"id": local_id, "reason": "Evento mudou durante a consulta / Event changed during query"})
                        continue
                    start = moment(incoming["due"])
                    end = moment(fresh.get("end", {}).get("dateTime"))
                    duration = end - start
                    if duration <= timedelta(0):
                        raise GoogleError("Duração remota inválida / Invalid remote duration")
                    client.request("PATCH", path + "/" + rid, params={"sendUpdates": "none"}, etag=fresh["etag"],
                        body={"summary": local["title"], "start": {"dateTime": local["due"]},
                              "end": {"dateTime": (moment(local["due"]) + duration).isoformat()}})
                    current = client.request("GET", path + "/" + rid)
                    incoming = snapshot(current, True) if current else None
                    if incoming != local:
                        raise GoogleError("Atualização remota não confirmada / Remote update unverified")
                    changes += 1
                if local != incoming:
                    event.update(incoming, dirty=True)  # Let Trello see the imported change too.
                    store.save(events)
                    changes += 1
                link["shadow"] = copy.deepcopy(incoming)
                write_secret(PATH, state)
            for rid, event in remote.items():
                if rid in linked:
                    continue
                incoming = snapshot(event, True)
                if incoming is None:
                    if event.get("status") != "cancelled":
                        issues.append({"id": rid, "reason": "Dia inteiro/recorrência omitido / All-day or recurrence omitted"})
                    continue
                if len(events) >= MAX_LOCAL:
                    issues.append({"id": rid, "reason": "Limite local atingido / Local limit reached"})
                    continue
                local_id = "google-" + hashlib.sha256((scope + rid).encode()).hexdigest()
                # Persist the link first. A restart can safely find this deterministic ID.
                state["links"][local_id] = {"id": rid, "shadow": copy.deepcopy(incoming)}
                write_secret(PATH, state)
                existing = next((e for e in events if e["id"] == local_id), None)
                if existing is None:
                    events.append({"id": local_id, **incoming, "dirty": True})
                    store.save(events)
                    changes += 1
            write_secret(PATH, state)
        return {"changes": changes, "issues": issues, "complete": not issues,
                "note": "Sincronização manual; sem convites, exclusão remota automática ou recorrências / Manual sync; no invitations, automatic remote deletion or recurrences"}
    finally:
        _sync_lock.release()
