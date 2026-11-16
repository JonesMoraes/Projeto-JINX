"""Local, conservative factual proposals. Only a human UI action persists them.

No model calls, disk-backed pending data, behavioural rules or tool acceptance.
Pending and declined proposals expire with this process; cap protects memory.
"""
from __future__ import annotations

import copy
import re
import threading
import uuid
from collections import deque

from core import undo
from memory import memory_manager as store

_lock = threading.RLock()
_pending = {}
_seen = deque(maxlen=128)
MAX_PENDING = 16
_SECRET = re.compile(r"senha|password|passwd|token|secret|api.?key|sk-[a-z0-9]|AIza|chave|credential", re.I)
_PATTERNS = (
    (r"(?:meu nome é|my name is) (.+)", "identity", "name"),
    (r"(?:eu moro em|moro em|i live in) (.+)", "identity", "city"),
    (r"(?:eu trabalho como|trabalho como|i work as) (.+)", "identity", "job"),
    (r"(?:meu projeto atual é|my current project is) (.+)", "projects", "current"),
)


def pending():
    with _lock:
        return copy.deepcopy(list(_pending.values()))


def observe(text, player=None):
    """Call only for completed user utterances, never model/tool/document text."""
    if not isinstance(text, str) or not 4 <= len(text) <= 240 or _SECRET.search(text):
        return []
    text = " ".join(text.split()).rstrip(".! ")
    # Whole sentence matching intentionally ignores quoted, conditional and multi-sentence data.
    if any(c in text for c in '\n?;:"<>') or re.search(r"[.!]\s|\b(?:se|if|mas|but)\b", text, re.I):
        return []
    for pattern, category, key in _PATTERNS:
        match = re.fullmatch(pattern, text, re.I)
        if not match:
            continue
        value = match[1].strip()
        if not 2 <= len(value) <= 100 or not re.fullmatch(r"[\wÀ-ÿ ,&()+/-]+", value):
            return []
        fingerprint = (category, key, value.casefold())
        with _lock:
            if fingerprint in _seen or len(_pending) >= MAX_PENDING:
                return []
            existing = store.load_memory().get(category, {}).get(key)
            if store._entry_value(existing).casefold() == value.casefold():
                return []
            row = dict(id=uuid.uuid4().hex[:12], category=category, key=key,
                       value=value, previous=copy.deepcopy(existing), source="local_heuristic")
            _pending[row['id']] = row
            _seen.append(fingerprint)
        if player is not None:
            try:
                player.write_log("SYS: Nova proposta de memória; revise em ⚙ → Memória. Nada salvo.")
            except Exception:
                pass
        return [copy.deepcopy(row)]
    return []


def reject(proposal_id):
    with _lock:
        return _pending.pop(proposal_id, None) is not None


def accept_from_ui(proposal_id):
    """Only called by the human's Approve button; deliberately absent from tools."""
    with _lock, store._lock:
        row = _pending.get(proposal_id)
        if row is None:
            raise ValueError("Proposta não encontrada; atualize a lista.")
        memory = store.load_memory()
        category, key = row['category'], row['key']
        if memory[category].get(key) != row['previous']:
            raise ValueError("Memória alterada desde a proposta. Rejeite e revise o fato atual.")
        before = copy.deepcopy(row['previous'])
        store.update_memory({category: {key: row['value']}})
        installed = copy.deepcopy(store.load_memory()[category].get(key))
        if store._entry_value(installed) != row['value']:
            raise OSError("Gravação de memória não confirmada.")
        _pending.pop(proposal_id)

    def restore():
        with store._lock:
            memory = store.load_memory()
            if memory[category].get(key) != installed:
                return "Memória mudou após aprovação; preservada."
            if before is None:
                memory[category].pop(key, None)
            else:
                memory[category][key] = before
            store.save_memory(memory)
        return "Memória anterior restaurada."
    undo.push_undo("memória aprovada", restore)
    return "Memória aprovada e salva."
