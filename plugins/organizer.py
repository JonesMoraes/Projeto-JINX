"""Tasks/agenda port adapted from João Gabriel, CC BY-NC 4.0; see NOTICE.md."""
import json
from datetime import datetime, timedelta
from core import outcome
from core import organizer_store as store, agenda_store

PLUGIN = {"name": "organizer", "description": "Local tasks and agenda CRUD, no account needed. Archive instead of permanent delete. Undo via existing undo tool. For plain timed alerts use reminder.",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["add", "list", "update", "complete", "reopen", "archive", "agenda"]},
        "kind": {"type": "STRING", "enum": ["task", "event"]},
        **{k: {"type": "STRING"} for k in ("title", "id", "new_title", "note")},
        "due": {"type": "STRING", "description": "ISO datetime; event date/time required; empty clears task due date"},
        "priority": {"type": "STRING", "enum": ["low", "normal", "high"]},
        "filter": {"type": "STRING", "enum": ["open", "done", "all", "today", "tomorrow", "overdue", "week"]}},
        "required": ["action"]}}


def _filtered(items, mode):
    today = datetime.now().astimezone().date()
    result = []
    for item in items:
        if mode != "all" and item.get("archived"):
            continue
        if mode == "open" and item.get("done"):
            continue
        if mode == "done" and not item.get("done"):
            continue
        if mode in ("today", "tomorrow", "week", "overdue"):
            if not item.get("due") or item.get("done"):
                continue
            due = datetime.fromisoformat(item["due"].replace("Z", "+00:00")).astimezone()
            day = due.date()
            match = {"today": day == today, "tomorrow": day == today + timedelta(days=1),
                     "week": today <= day < today + timedelta(days=7),
                     "overdue": due < datetime.now().astimezone()}[mode]
            if not match:
                continue
        result.append(item)
    return result


def run(parameters, player=None, session_memory=None):
    p = parameters or {}
    try:
        action, kind = p.get("action"), p.get("kind", "task")
        if kind not in ("task", "event"):
            raise ValueError("kind")
        if action in ("list", "agenda"):
            items = (agenda_store.all_events(True) if kind == "event" else store.tasks())
            if action == "agenda":
                items = [{**t, "kind": "task"} for t in store.tasks()] + [
                    {**e, "kind": "event"} for e in agenda_store.all_events(True)]
            mode = p.get("filter") or ("today" if action == "agenda" else "open")
            if mode not in ("open", "done", "all", "today", "tomorrow", "overdue", "week"):
                raise ValueError("filter")
            selected = sorted(_filtered(items, mode), key=lambda x: x.get("due") or "9999")
            return outcome.done("organizer", count=len(selected), data=outcome.untrusted(
                "organizer", json.dumps(selected, ensure_ascii=False)))
        if kind == "event":
            if action not in ("add", "update", "archive"):
                raise ValueError("event action")
            title = p.get("title")
            event_id = None
            if action != "add":
                event = store.pick(agenda_store.all_events(), p.get("id") or title)
                title = event["title"]
                event_id = event["id"]
            from plugins.agenda import run as agenda_run
            return agenda_run({"action": {"add": "add", "update": "reschedule", "archive": "archive"}[action],
                               "title": title, "id": event_id, "due": p.get("due"), "new_title": p.get("new_title")}, player, session_memory)
        fields = {k: p[k] for k in ("due", "priority", "note") if k in p}
        if "new_title" in p:
            fields["title"] = p["new_title"]
        item = store.change(action, p.get("id") or p.get("title", ""), **fields)
        return outcome.done("organizer", data=outcome.untrusted("organizer", json.dumps(item, ensure_ascii=False)))
    except ValueError:
        return outcome.failed("organizer", "Dados inválidos ou título ambíguo; liste os itens e use o ID / Invalid data or ambiguous title; list items and use ID")
    except Exception:
        return outcome.failed("organizer", "Falha ao acessar dados; arquivo preservado / Data access failed; file preserved")
