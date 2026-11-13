"""Agenda/Trello reconciliation adapted from jgm-source; see NOTICE.md.

Conflicts preserve both versions. A disappearing card never deletes local data.
"""
import hashlib
import threading
from datetime import datetime
from core import outcome, trello_client as api, agenda_store as store
from memory.config_manager import get_plugin_config, get_plugin_enabled

_stop = threading.Event()
_thread = None
_start_lock = threading.Lock()
_sync_lock = threading.Lock()


def canonical_due(value):
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone().isoformat()


def snapshot(card):
    return {"title": str(card.get("name") or ""), "due": canonical_due(card.get("due"))}


def sync_now():
    cfg = get_plugin_config("agenda")
    if not get_plugin_enabled("agenda_sync") or not cfg.get("enabled") or not cfg.get("list_id"):
        return outcome.unverified("agenda_sync", "Sincronização desligada / Sync disabled")
    if not _sync_lock.acquire(blocking=False):
        return outcome.unverified("agenda_sync", "Sincronização em andamento / Sync running")
    try:
        list_id = api.ident(cfg["list_id"])
        credentials = get_plugin_config("trello")
        scope = hashlib.sha256((str(credentials.get("api_key")) + "|" +
            str(credentials.get("token")) + "|" + list_id).encode()).hexdigest()
        remote_list = api.cards(list_id)
        # A suspicious full response must never be treated as proof of absence.
        if len(remote_list) >= 1000:
            return outcome.unverified("agenda_sync", "Lista muito grande; reconciliação suspensa / List too large")
        remote = {c["id"]: c for c in remote_list}
        count = 0
        conflicts = 0
        with store.lock:
            events = store.load()
            if any(e.get("trello_id") and e.get("trello_scope") != scope for e in events):
                return outcome.failed("agenda_sync", "Conta/lista mudou; revise os vínculos / Account or list changed; review links")
            linked = set()
            for event in events:
                cid = event.get("trello_id")
                if not cid:
                    marker = "JINX agenda:" + event["id"]
                    matches = [c for c in remote_list if marker in str(c.get("desc") or "")]
                    if len(matches) == 1:
                        cid = matches[0]["id"]
                    elif event.get("creating") or len(matches) > 1:
                        event["sync_issue"] = "Criação pendente de verificação / Creation needs verification"
                        conflicts += 1
                        continue
                    else:
                        # Durable before POST: a timeout cannot cause duplicate cards.
                        event["creating"] = True
                        store.save(events)
                        created = api.request("POST", "/cards", {"idList": list_id,
                            "name": event["title"], "due": event["due"], "desc": marker})
                        cid = created["id"]
                    verified = api.card(cid)
                    if verified.get("idList") != list_id or marker not in str(verified.get("desc") or ""):
                        raise api.TrelloError("Vínculo não verificado / Link not verified")
                    event.update(trello_id=cid, trello_scope=scope, shadow=snapshot(verified),
                                 creating=False, dirty=(snapshot(verified) != {
                                     "title": event["title"], "due": canonical_due(event["due"])}))
                    remote[cid] = verified
                    count += 1
                linked.add(cid)
                current = remote.get(cid)
                if current is None or current.get("closed"):
                    event["sync_issue"] = "Cartão ausente ou arquivado; evento preservado / Card missing; event preserved"
                    conflicts += 1
                    continue
                incoming = snapshot(current)
                previous = event.get("shadow")
                local = {"title": event["title"], "due": canonical_due(event["due"])}
                if event.get("dirty") and previous is not None and incoming != previous and incoming != local:
                    event["sync_issue"] = "Conflito local/remoto; dados preservados / Local/remote conflict"
                    conflicts += 1
                    continue
                if event.get("dirty"):
                    current = api.update(cid, {"name": event["title"], "due": event["due"]})
                    incoming = snapshot(current)
                    count += 1
                if incoming["due"] is None:
                    event["sync_issue"] = "Prazo remoto removido; evento preservado / Remote due date removed"
                    conflicts += 1
                    continue
                event.update(incoming)
                event.update(shadow=incoming, dirty=False)
                event.pop("sync_issue", None)
                store.save(events)
            for cid, card in remote.items():
                if cid in linked or card.get("closed") or not card.get("due"):
                    continue
                value = snapshot(card)
                events.append({"id": "trello-" + cid, **value, "trello_id": cid,
                    "trello_scope": scope, "shadow": value, "dirty": False})
                count += 1
            store.save(events)
        if conflicts:
            return outcome.unverified("agenda_sync", "Há pendências preservadas / Pending items preserved", conflicts=conflicts)
        return outcome.done("agenda_sync", changes=count)
    except Exception:
        return outcome.unverified("agenda_sync", "Falha; dados locais preservados / Failure; local data preserved")
    finally:
        _sync_lock.release()


def start(log=None):
    global _thread
    with _start_lock:
        if _thread and _thread.is_alive():
            return
        _stop.clear()
        def loop():
            while not _stop.wait(60):
                if get_plugin_config("agenda").get("enabled"):
                    result = sync_now()
                    if log:
                        log(result)
        _thread = threading.Thread(target=loop, name="agenda-sync", daemon=True)
        _thread.start()


def stop():
    _stop.set()
