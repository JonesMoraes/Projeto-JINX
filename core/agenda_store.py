"""Minimal shared agenda persistence for Trello sync; task CRUD follows in 1.3."""
import copy
import json
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / "memory" / "agenda.json"
lock = threading.RLock()


def load():
    if not PATH.exists():
        return []
    data = json.loads(PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Agenda inválida; arquivo preservado / Invalid agenda; file preserved")
    return data


def save(events):
    PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = PATH.with_suffix(".json.tmp")
    temp.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, PATH)


def all_events(include_archived=False):
    with lock:
        return copy.deepcopy([e for e in load() if include_archived or not e.get("archived")])


def upsert(title, due, event_id=None):
    parsed = datetime.fromisoformat(str(due).replace("Z", "+00:00"))
    due = parsed.astimezone().isoformat()
    title = str(title or "").strip()
    if not title:
        raise ValueError("Título obrigatório / Title required")
    with lock:
        events = load()
        event = next((e for e in events if e["id"] == event_id), None)
        if event_id and not event:
            raise ValueError("Evento não encontrado / Event not found")
        if event is None:
            event = {"id": uuid.uuid4().hex}
            events.append(event)
        event.update(title=title, due=due, dirty=True)
        save(events)
        return copy.deepcopy(event)


def archive(event_id, archived=True):
    with lock:
        events = load()
        item = next((e for e in events if e["id"] == event_id), None)
        if item is None:
            raise ValueError("Evento não encontrado / Event not found")
        item.update(archived=bool(archived), dirty=True)
        save(events)
        return copy.deepcopy(item)
