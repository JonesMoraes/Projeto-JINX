"""Small thread-safe event bus for coordinating JINX subsystems.

Subscribers run on the publishing thread. UI subscribers must hand work to the
Qt thread through JinxUI signals; this module never imports or touches Qt.
"""
from __future__ import annotations

import logging
import threading
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any

_log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Event:
    """Immutable event envelope; payload data is copied at publication."""

    name: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class EventBus:
    """In-process pub/sub with safe subscribe/unsubscribe during dispatch."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscribers: dict[str, list[Callable[[Event], None]]] = defaultdict(list)

    def subscribe(self, name: str, callback: Callable[[Event], None]) -> Callable[[], None]:
        """Subscribe to one event name or ``*``; return an idempotent remover."""
        event_name = str(name or "").strip()
        if not event_name:
            raise ValueError("event name is required")
        if not callable(callback):
            raise TypeError("callback must be callable")
        with self._lock:
            self._subscribers[event_name].append(callback)

        removed = False
        remove_lock = threading.Lock()

        def unsubscribe() -> None:
            nonlocal removed
            with remove_lock:
                if removed:
                    return
                removed = True
            with self._lock:
                callbacks = self._subscribers.get(event_name, [])
                try:
                    callbacks.remove(callback)
                except ValueError:
                    pass
                if not callbacks:
                    self._subscribers.pop(event_name, None)

        return unsubscribe

    def publish(self, name: str, /, **payload: Any) -> Event:
        """Publish synchronously, isolating subscriber failures from callers."""
        event_name = str(name or "").strip()
        if not event_name:
            raise ValueError("event name is required")
        event = Event(event_name, MappingProxyType(dict(payload)))
        with self._lock:
            callbacks = tuple(self._subscribers.get(event_name, ())) + tuple(
                self._subscribers.get("*", ()))
        for callback in callbacks:
            try:
                callback(event)
            except Exception:
                _log.exception("JINX event subscriber failed for %s", event_name)
        return event

    def clear(self) -> None:
        """Remove all subscriptions, useful when an owning runtime shuts down."""
        with self._lock:
            self._subscribers.clear()
