"""Opt-in local presence detection; never identifies people or stores frames."""
from __future__ import annotations

import threading

_lock = threading.RLock()
_enabled = False
_cascade = None
_frames = 0
_last_present = None
_notify = None


def start(notify=None) -> str:
    global _enabled, _cascade, _frames, _last_present, _notify
    try:
        import cv2
        path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        cascade = cv2.CascadeClassifier(path)
        if cascade.empty(): return "Presence model unavailable."
    except Exception as exc:
        return f"Presence detection unavailable: {type(exc).__name__}."
    with _lock:
        _enabled, _cascade, _frames, _last_present, _notify = True, cascade, 0, None, notify
    return "Presence monitor on. Local camera only; no identity, images or upload."


def stop() -> None:
    global _enabled, _cascade, _last_present, _notify
    with _lock:
        _enabled, _cascade, _last_present, _notify = False, None, None, None


def active() -> bool:
    with _lock: return _enabled


def feed(frame) -> None:
    global _frames, _last_present
    with _lock:
        if not _enabled: return
        _frames += 1
        if _frames % 12: return
        cascade, notify = _cascade, _notify
    try:
        import cv2
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (320, 180), interpolation=cv2.INTER_AREA)
        present = len(cascade.detectMultiScale(small, scaleFactor=1.15,
                                               minNeighbors=5, minSize=(24, 24))) > 0
    except Exception:
        return
    with _lock:
        if not _enabled or present == _last_present: return
        _last_present = present
    if notify:
        try: notify("Pessoa detectada" if present else "Área sem pessoa detectada")
        except Exception: pass
