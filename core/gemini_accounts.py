"""Primary-first Gemini account fallback, inspired by jgm-source's port.

Configuration stays in config_manager; only fingerprints enter cooldown state.
"""
from __future__ import annotations

import hashlib
import threading
import time
from memory.config_manager import load_api_keys

_lock = threading.RLock()
_rest: dict[str, float] = {}
QUOTA_REST = 30 * 60
REJECTED_REST = 6 * 60 * 60


def _id(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def configured() -> list[str]:
    data = load_api_keys()
    plugins = data.get("plugin_config")
    extras = plugins.get("gemini", {}) if isinstance(plugins, dict) else {}
    if not isinstance(extras, dict):
        extras = {}
    values = [data.get("gemini_api_key"), extras.get("secondary_key"),
              extras.get("tertiary_key")]
    return list(dict.fromkeys(str(v).strip() for v in values if str(v or "").strip()))


def available() -> list[str]:
    keys = configured()
    with _lock:
        now = time.monotonic()
        return [key for key in keys if _rest.get(_id(key), 0) <= now]


def select() -> str:
    keys = available()
    return keys[0] if keys else ""


def rest(key: str, rejected: bool = False) -> None:
    with _lock:
        _rest[_id(key)] = time.monotonic() + (REJECTED_REST if rejected else QUOTA_REST)


def status(english: bool = False) -> str:
    keys = configured()
    if not keys:
        return "No Gemini keys configured." if english else "Nenhuma chave Gemini configurada."
    active = select()
    rows = []
    with _lock:
        for i, key in enumerate(keys, 1):
            remaining = max(0, int(_rest.get(_id(key), 0) - time.monotonic()))
            state = ((f"resting {remaining // 60 + 1} min" if english else
                      f"em pausa por {remaining // 60 + 1} min") if remaining else
                     ("active" if english else "ativa") if key == active else
                     ("ready" if english else "disponível"))
            rows.append(f"{i}: {state}")
    return "; ".join(rows)


def attempt(operation, explicit_key: str = ""):
    """Retry the same model with another account on quota/key rejection only.

    External caller credentials are isolated. Existing actions that explicitly
    pass the configured primary still participate in the configured fallback.
    No provider/network work is done while holding the cooldown lock.
    """
    from core.gemini import is_key_error, is_quota_error
    external = bool(explicit_key and explicit_key not in configured())
    keys = [explicit_key] if external else available()
    if not keys:
        raise RuntimeError("Gemini accounts are resting or not configured")
    for key in keys:
        if not external and key not in available():
            continue
        try:
            return operation(key)
        except Exception as exc:
            rejected = is_key_error(str(exc))
            if not rejected and not is_quota_error(str(exc)):
                raise
            if not external:
                rest(key, rejected)
    raise RuntimeError("Gemini accounts unavailable") from None
