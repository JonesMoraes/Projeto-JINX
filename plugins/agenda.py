"""Local agenda tools with explicit Google Calendar synchronization by default."""
import json
from core import outcome, undo
from core import agenda_store as store, agenda_sync
from core.plugin_jobs import Jobs

_google_jobs = Jobs('Google Agenda')

PLUGIN = {"name": "agenda_sync", "description": "Agenda: list/add/reschedule/archive local events; explicitly sync with Google Calendar. Local edits do not automatically publish to Google. Connect account in Agenda settings. Trello is a separate optional tool, not the default agenda. Archive/undo are local and do not delete Google events.",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["list", "add", "reschedule", "archive", "sync"]},
        "title": {"type": "STRING"},
        "id": {"type": "STRING"},
        "new_title": {"type": "STRING"},
        "due": {"type": "STRING", "description": "ISO datetime, e.g. 2026-11-14T17:00:00-03:00; rescheduling must retain the event date"}},
        "required": ["action"]}}

PLUGIN_SETTINGS = {"namespace": "agenda", "title": "AGENDA — GOOGLE AGENDA / GOOGLE CALENDAR",
    "fields": [],
    "action": {"label": "TESTAR GOOGLE AGENDA (CONECTE PELO PAINEL AGENDA)", "run": lambda values: _test(values)}}


def _test(values):
    from core import google_workspace as api
    try:
        client = api.Client('calendar')
        result = client.request('GET', api.calendar_path(api.config().get('calendar_id')), params={'maxResults': 1})
        return isinstance(result, dict), 'Google Agenda acessível.' if isinstance(result, dict) else 'Calendário não encontrado.'
    except api.GoogleError as exc:
        return False, str(exc)
    except Exception:
        return False, 'Não foi possível verificar o Google Agenda.'


def run(parameters, player=None, session_memory=None):
    p = parameters or {}
    try:
        action = p.get("action")
        if action == "sync":
            if agenda_sync.provider() == 'trello':
                return agenda_sync.sync_now()
            return _google_jobs.start(lambda: agenda_sync.display_result(agenda_sync.sync_now()), player)
        if action == "list":
            return outcome.done("agenda", data=outcome.untrusted("agenda", json.dumps(store.all_events(), ensure_ascii=False)))
        if action not in ("add", "reschedule", "archive"):
            return outcome.failed("agenda", "Ação desconhecida / Unknown action")
        previous = None
        if action in ("reschedule", "archive"):
            matches = [e for e in store.all_events() if e["id"] == p["id"]] if p.get("id") else [
                e for e in store.all_events() if e["title"].casefold() == str(p.get("title", "")).casefold()]
            if len(matches) != 1:
                return outcome.failed("agenda", "Título ausente ou ambíguo / Missing or ambiguous title")
            previous = matches[0]
            p = {**p, "title": previous["title"]}
        if action == "archive":
            event = store.archive(previous["id"])
        else:
            event = store.upsert(p.get("new_title") or p.get("title"),
                                 p.get("due") or (previous["due"] if previous else None),
                                 previous["id"] if previous else None)
        def restore():
            with store.lock:
                events = store.load()
                item = next((e for e in events if e["id"] == event["id"]), None)
                if (not item or any(item.get(k) != event.get(k) for k in ("title", "due"))
                        or bool(item.get("archived")) != bool(event.get("archived"))):
                    return outcome.failed("agenda_undo", "Evento mudou / Event changed")
                if previous:
                    item.update(title=previous["title"], due=previous["due"],
                                archived=previous.get("archived", False), dirty=True)
                    if action == "archive" and item.get("trello_id") and agenda_sync.provider() == 'trello':
                        item["restore_remote"] = True
                elif item.get("trello_id") and agenda_sync.provider() == 'trello':
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
        if agenda_sync.provider() == 'trello':
            return outcome.done("agenda_local", id=event["id"], sync=agenda_sync.sync_now())
        return outcome.done('agenda_local', id=event['id'],
                            note='Alteração salva localmente. Use Sincronizar com Google para enviar/receber eventos. Arquivar/desfazer não apaga eventos no Google.')
    except ValueError:
        return outcome.failed("agenda", "Informe título e data/hora ISO válidos / Provide title and valid ISO datetime")
    except Exception:
        return outcome.failed("agenda", "Falha local / Local failure")
