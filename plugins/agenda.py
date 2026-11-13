"""Agenda sync voice hooks; organizer task CRUD follows in expansion 1.3."""
import json
from core import outcome, undo
from core import agenda_store as store, agenda_sync

PLUGIN = {"name": "agenda_sync", "description": "Agenda: list, add, reschedule by title; sync with user's Trello list.",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["list", "add", "reschedule", "sync"]},
        "title": {"type": "STRING"},
        "due": {"type": "STRING", "description": "ISO datetime, e.g. 2026-11-14T17:00:00-03:00; rescheduling must retain the event date"}},
        "required": ["action"]}}

PLUGIN_SETTINGS = {"namespace": "agenda", "title": "AGENDA — SUA LISTA TRELLO / YOUR TRELLO LIST",
    "fields": [{"key": "enabled", "label": "Sincronizar a cada 60 s / Sync every 60 s", "type": "toggle", "default": False},
               {"key": "list_id", "label": "ID da sua lista Trello / Your Trello list ID", "type": "text"}],
    "action": {"label": "TESTAR LISTA / TEST LIST", "run": lambda values: _test(values)}}


def _test(values):
    from core import trello_client as api
    try:
        result = api.request("GET", "/lists/" + api.ident(values.get("list_id")), {"fields": "id"})
        return bool(result.get("id")), "Lista acessível pela sua conta / List accessible to your account"
    except api.TrelloError as exc:
        return False, str(exc)


def run(parameters, player=None, session_memory=None):
    p = parameters or {}
    try:
        action = p.get("action")
        if action == "sync":
            return agenda_sync.sync_now()
        if action == "list":
            return outcome.done("agenda", data=outcome.untrusted("agenda", json.dumps(store.all_events(), ensure_ascii=False)))
        if action not in ("add", "reschedule"):
            return outcome.failed("agenda", "Ação desconhecida / Unknown action")
        previous = None
        if action == "reschedule":
            matches = [e for e in store.all_events() if e["title"].casefold() == str(p.get("title", "")).casefold()]
            if len(matches) != 1:
                return outcome.failed("agenda", "Título ausente ou ambíguo / Missing or ambiguous title")
            previous = matches[0]
        event = store.upsert(p.get("title"), p.get("due"), previous["id"] if previous else None)
        def restore():
            with store.lock:
                events = store.load()
                item = next((e for e in events if e["id"] == event["id"]), None)
                if not item or item.get("title") != event["title"] or item.get("due") != event["due"]:
                    return outcome.failed("agenda_undo", "Evento mudou / Event changed")
                if previous:
                    item.update(title=previous["title"], due=previous["due"], dirty=True)
                elif item.get("trello_id"):
                    from core import trello_client as api
                    import hashlib
                    from memory.config_manager import get_plugin_config
                    config = get_plugin_config("agenda")
                    credentials = get_plugin_config("trello")
                    current_scope = hashlib.sha256((str(credentials.get("api_key")) + "|" +
                        str(credentials.get("token")) + "|" + str(config.get("list_id"))).encode()).hexdigest()
                    if item.get("trello_scope") != current_scope:
                        return outcome.failed("agenda_undo", "Conta/lista alterada / Account or list changed")
                    remote = api.card(item["trello_id"])
                    if agenda_sync.snapshot(remote) != {"title": event["title"], "due": event["due"]}:
                        return outcome.failed("agenda_undo", "Cartão remoto mudou / Remote card changed")
                    api.update(item["trello_id"], {"closed": True})
                    events.remove(item)
                else:
                    events.remove(item)
                store.save(events)
            return outcome.done("agenda_undo")
        undo.push_undo("Agenda", restore)
        result = agenda_sync.sync_now()
        return outcome.done("agenda_local", id=event["id"], sync=result)
    except ValueError:
        return outcome.failed("agenda", "Informe título e data/hora ISO válidos / Provide title and valid ISO datetime")
    except Exception:
        return outcome.failed("agenda", "Falha local / Local failure")
