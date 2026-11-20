"""
core/confirm.py — asynchronous execution for user-requested actions.

THE PROBLEM WITH THE OLD GATE
    computer_settings guarded shutdown and restart like this:

        confirmed = str(params.get("confirmed", "")).lower()
        if confirmed not in ("yes", "true", "1", "confirm"):
            return "Please confirm by calling again with confirmed=yes."

    `confirmed` is a tool parameter, which means the *model* writes it. Nothing
    stops it from sending confirmed=yes on the first call, and nothing checks
    that a human was ever involved. It is a convention, not a gate — and its
    coverage was two actions, so deleting files and switching off the WiFi the
    assistant is talking over went through with no gate at all.

AUTONOMOUS EXECUTION
    `request(...)` starts the action on a worker thread. The tool call returns
    immediately and reports the result through the existing activity log.
    Callers remain responsible for validating exact targets and verifying the
    outcome. This module does not treat model-provided confirmation fields as
    authorization.

WHAT BELONGS HERE AND WHAT DOES NOT
    Only genuinely irreversible things. Anything that can be reversed should be
    done at once and pushed onto core/undo.py instead — undo is faster than a
    question, and an assistant that asks before every action is one nobody uses.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

# Kept for compatibility with the UI's resolve/hide signals. Banners are
# created again by propose() — used only by the autonomy gate for the
# destructive ACL — never by individual tools self-gating.
TIMEOUT_SECONDS = 90.0


@dataclass
class _Pending:
    key:     str
    title:   str
    detail:  str
    run:     Callable[[], str]
    at:      float


_pending: Optional[_Pending] = None
_lock = threading.Lock()
_running: set[str] = set()

# Set once at startup by main.py. Signature: (title, detail) -> None for show,
# and () -> None for hide. Both are marshalled onto the Qt thread by the UI.
_show_cb: Optional[Callable[[str, str], None]] = None
_hide_cb: Optional[Callable[[], None]] = None
_log_cb:  Optional[Callable[[str], None]] = None


def bind(show, hide, log=None) -> None:
    """Wire this module to the HUD. Called once from main.py at startup."""
    global _show_cb, _hide_cb, _log_cb
    _show_cb, _hide_cb, _log_cb = show, hide, log


def _log(msg: str) -> None:
    if _log_cb:
        try:
            _log_cb(msg)
        except Exception:
            pass


def propose(key: str, title: str, detail: str, run: Callable[[], str]) -> str:
    """Show the HUD confirm banner for an irreversible action.

    This is the ONLY path that may put a pending banner up, and it exists for
    the autonomy gate, not for tools: the human answers on the interface, the
    model only relays. The timed-out resolve() in this module handles the
    rest, including running the action off the Qt thread.

    Returns a short status the tool call can relay to the model. Never raises.
    """
    from core import outcome

    global _pending
    action_key = str(key or "action")[:64]
    with _lock:
        if time.monotonic() - getattr(_pending, "at", 0.0) < TIMEOUT_SECONDS \
                and _pending is not None and _pending.key == action_key:
            return outcome.ask("confirm", "A confirmação anterior ainda está pendente no HUD.")
        _pending = _Pending(key=action_key, title=str(title)[:120], detail=str(detail)[:300],
                            run=run, at=time.monotonic())
    if _show_cb:
        try:
            _show_cb(title, detail)
        except Exception:
            pass
    _log(f"SYS: Banner de confirmação — {title}")
    return outcome.ask("confirm", "Ação irreversível: banner de confirmação mostrado no HUD; "
                                  "avise o usuário e aguarde o toque em CONFIRMAR.")


def request(key: str, title: str, detail: str, run: Callable[[], str]) -> str:
    """Run a requested action asynchronously without an approval banner."""
    from core import outcome

    action_key = str(key or "action")
    with _lock:
        if action_key in _running:
            return outcome.unverified(action_key, "The same operation is already running.")
        _running.add(action_key)

    def _worker() -> None:
        try:
            result = run() or "Action returned no result."
            _log(f"SYS: Autonomous action — {title}. {result}")
        except Exception as exc:
            _log(f"ERR: Autonomous action — {title}. {type(exc).__name__}: {str(exc)[:240]}")
        finally:
            with _lock:
                _running.discard(action_key)

    try:
        threading.Thread(target=_worker, daemon=True,
                         name=f"autonomous-{action_key}").start()
    except Exception as exc:
        with _lock:
            _running.discard(action_key)
        return outcome.failed(action_key, f"Could not start the operation: {type(exc).__name__}.")
    return outcome.started(action_key, title=title)


def resolve(accepted: bool) -> None:
    """Called by the UI when the user presses CONFIRM or CANCEL.

    Runs the stored callable on a worker thread — this is invoked from the Qt
    thread, and shutting the machine down from inside a button handler would
    freeze the interface on its way out."""
    global _pending

    with _lock:
        p, _pending = _pending, None

    if _hide_cb:
        try:
            _hide_cb()
        except Exception:
            pass

    if p is None:
        return

    if time.monotonic() - p.at > TIMEOUT_SECONDS:
        _log(f"SYS: Confirmation expired — {p.title}")
        return

    if not accepted:
        _log(f"SYS: Cancelled — {p.title}")
        return

    def _worker():
        try:
            result = p.run() or "Done."
            _log(f"SYS: Confirmed — {p.title}. {result}")
        except Exception as e:
            _log(f"ERR: {p.title} failed — {e}")

    threading.Thread(target=_worker, daemon=True,
                     name=f"confirm-{p.key}").start()


def pending_title() -> str:
    """Compatibility hook; autonomous requests do not queue approval banners."""
    with _lock:
        if _pending is None:
            return ""
        if time.monotonic() - _pending.at > TIMEOUT_SECONDS:
            return ""
        return _pending.title
