"""Local tasks, adapted from jgm-source's organizer; see NOTICE.md.

Per-item undo preserves unrelated changes. Corrupt files are never overwritten.
"""
import copy
import json
import os
import threading
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path
from core import outcome, undo

PATH = Path(__file__).resolve().parent.parent / "memory" / "organizer.json"
_lock = threading.RLock()


def fold(value):
    return "".join(c for c in unicodedata.normalize("NFKD", str(value).casefold())
                   if not unicodedata.combining(c)).strip()


def pick(items, selector):
    query = fold(selector)
    for match in (lambda x: x.get("id") == selector,
                  lambda x: fold(x.get("title")) == query,
                  lambda x: fold(x.get("title")).startswith(query)):
        found = [x for x in items if query and match(x)]
        if len(found) == 1:
            return found[0]
        if len(found) > 1:
            break
    raise ValueError("Título ausente ou ambíguo; use o ID / Missing or ambiguous title; use ID")


def _load():
    if not PATH.exists():
        return {"tasks": []}
    data = json.loads(PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
        raise ValueError("Arquivo inválido; preservado / Invalid file; preserved")
    return data


def _save(data):
    PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = PATH.with_suffix(".json.tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, PATH)
    if _load() != data:
        raise OSError("Write not verified")


def tasks():
    with _lock:
        return copy.deepcopy(_load()["tasks"])


def change(action, selector="", **fields):
    with _lock:
        data = _load()
        items = data["tasks"]
        before = None
        if action == "add":
            item = {"id": uuid.uuid4().hex, "title": selector, "done": False,
                    "archived": False, "priority": "normal", "due": None, "revision": 0}
            items.append(item)
        else:
            item = pick([x for x in items if not x.get("archived")], selector)
            before = copy.deepcopy(item)
        if action in ("add", "update"):
            item.update({k: v for k, v in fields.items() if k in ("title", "due", "priority", "note")})
            item["title"] = str(item.get("title") or "").strip()
            if not item["title"]:
                raise ValueError("Título obrigatório / Title required")
            if item.get("due"):
                item["due"] = datetime.fromisoformat(str(item["due"]).replace("Z", "+00:00")).astimezone().isoformat()
            if item["priority"] not in ("low", "normal", "high"):
                raise ValueError("Prioridade inválida / Invalid priority")
        elif action in ("complete", "reopen"):
            item["done"] = action == "complete"
        elif action == "archive":
            item["archived"] = True
        else:
            raise ValueError("Ação inválida / Invalid action")
        item["revision"] = int(item.get("revision", 0)) + 1
        after = copy.deepcopy(item)
        _save(data)
        def restore():
            with _lock:
                current_data = _load()
                current = next((x for x in current_data["tasks"] if x["id"] == after["id"]), None)
                if current != after:
                    return outcome.failed("organizer_undo", "Tarefa mudou / Task changed")
                if before is None:
                    current_data["tasks"].remove(current)
                else:
                    current.clear()
                    current.update(before)
                _save(current_data)
            return outcome.done("organizer_undo")
        undo.push_undo("Organizador / Organizer", restore)
        return after
