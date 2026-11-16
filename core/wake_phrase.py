"""Offline phrase gate for JINX.

The microphone frames stay on the device while JINX sleeps. Vosk performs
streaming recognition locally and only the three configured wake phrases call
on_detect. No Gemini or hosted transcription is used here.
"""
from __future__ import annotations

import json
import os
import queue
import re
import threading
import unicodedata
from pathlib import Path
from typing import Callable

SAMPLE_RATE = 16_000
WAKE_PHRASES = ("ei jinx", "ola jinx", "jinx")
_MAX_TRANSCRIPT = 240


def normalize_phrase(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or "").lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[a-z0-9]+", text))


def is_wake_phrase(text: str) -> bool:
    normalized = f" {normalize_phrase(text)} "
    return any(f" {phrase} " in normalized for phrase in WAKE_PHRASES)


def _candidate_model_paths() -> list[Path]:
    root = Path(__file__).resolve().parent.parent
    candidates = []
    configured = os.environ.get("JINX_VOSK_MODEL", "").strip()
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend((
        root / "models" / "vosk-model-small-pt-0.3",
        root / "models" / "vosk-model-small-pt",
        root / "models" / "vosk-model-pt",
    ))
    return candidates


def model_path() -> Path | None:
    for path in _candidate_model_paths():
        if path.is_dir():
            return path
    return None


def is_ready() -> bool:
    try:
        import importlib.util
        return (importlib.util.find_spec("vosk") is not None
                and model_path() is not None)
    except Exception:
        return False


def install_and_download(logger: Callable[[str], None] = print,
                         notify: Callable[[str], None] | None = None) -> tuple[bool, str]:
    """Return setup guidance without silently installing or downloading models."""
    message = (
        "Instale Vosk e coloque um modelo português em models/vosk-model-small-pt-0.3 "
        "ou defina JINX_VOSK_MODEL para a pasta do modelo."
    )
    logger(f"Wake phrase: {message}")
    if notify:
        notify(message)
    return False, message


class LocalWakePhraseDetector:
    """Bounded background Vosk recognizer used only while JINX is asleep."""

    def __init__(self, on_detect: Callable[[], None],
                 logger: Callable[[str], None] = print,
                 notify: Callable[[str], None] | None = None):
        self._on_detect = on_detect
        self._logger = logger
        self._notify = notify or (lambda _message: None)
        self._queue: queue.Queue = queue.Queue(maxsize=100)
        self._thread: threading.Thread | None = None
        self._running = False
        self._ready = False
        self._model = None
        self._recognizer = None

    @property
    def ready(self) -> bool:
        return self._ready

    def start(self) -> bool:
        if self._running:
            return True
        path = model_path()
        if path is None:
            self._notify("Wake phrase unavailable: Vosk Portuguese model not found.")
            return False
        try:
            from vosk import KaldiRecognizer, Model
            self._model = Model(str(path))
            self._recognizer = self._make_recognizer(KaldiRecognizer)
        except Exception as exc:
            self._logger(f"Wake phrase: could not load Vosk model — {exc}")
            self._notify("Wake phrase unavailable: Vosk could not load the model.")
            self._model = None
            self._recognizer = None
            return False
        self._running = True
        self._ready = True
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="JinxWakePhraseThread")
        self._thread.start()
        self._logger("Wake phrase: listening locally for 'Ei JINX', 'Olá JINX' or 'JINX'.")
        return True

    def stop(self) -> None:
        self._running = False
        try:
            self._queue.put_nowait(None)
        except Exception:
            pass
        self._ready = False
        self._model = None
        self._recognizer = None

    def reset(self) -> None:
        try:
            while True:
                self._queue.get_nowait()
        except Exception:
            pass
        try:
            from vosk import KaldiRecognizer
            if self._model is not None:
                self._recognizer = self._make_recognizer(KaldiRecognizer)
        except Exception:
            pass

    def _make_recognizer(self, recognizer_type):
        """Prefer a small local grammar, with compatibility fallback."""
        grammar = json.dumps([*WAKE_PHRASES, "[unk]"])
        try:
            return recognizer_type(self._model, SAMPLE_RATE, grammar)
        except TypeError:
            return recognizer_type(self._model, SAMPLE_RATE)

    def feed(self, frame_int16) -> None:
        if not self._running:
            return
        try:
            data = frame_int16[:, 0].tobytes() if getattr(frame_int16, "ndim", 1) > 1 \
                else frame_int16.tobytes()
            self._queue.put_nowait(data)
        except (queue.Full, AttributeError, TypeError):
            pass
        except Exception:
            pass

    def _loop(self) -> None:
        while self._running:
            try:
                data = self._queue.get()
                if data is None or not self._running:
                    break
                accepted = self._recognizer.AcceptWaveform(data)
                if accepted:
                    payload = json.loads(self._recognizer.Result() or "{}")
                    text = str(payload.get("text") or "")[:_MAX_TRANSCRIPT]
                else:
                    payload = json.loads(self._recognizer.PartialResult() or "{}")
                    text = str(payload.get("partial") or "")[:_MAX_TRANSCRIPT]
                if text:
                    self._logger(f"Wake phrase heard locally: {text}")
                if is_wake_phrase(text):
                    self.reset()
                    self._on_detect()
            except Exception as exc:
                self._logger(f"Wake phrase: recognition error — {exc}")
