"""Opt-in, CPU-only sustained speech gate; no I/O on the audio callback."""
import time
from collections import deque
from memory.config_manager import get_plugin_config

_enabled = False


def enabled():
    return _enabled


def configure(values=None):
    global _enabled
    cfg = get_plugin_config('barge_in') if values is None else values
    _enabled = cfg.get('enabled') is True
    return True, 'Interrupção por voz ' + ('ativada / enabled' if _enabled else 'desativada / disabled')


class Gate:
    def __init__(self):
        self._audio = deque(maxlen=32)
        self.count = 0
        self.since = None
        self.fired = False
        self.last_detection_ms = None

    def reset(self):
        self.count, self.since, self.fired = 0, None, False
        self._audio.clear()

    def take_audio(self):
        """Consume the sustained speech once, preserving the start of a phrase."""
        audio = tuple(self._audio)
        self._audio.clear()
        return audio

    def feed(self, echo, pcm, sample_rate, level, *, speaking, allowed, now=None):
        now = time.monotonic() if now is None else now
        if not _enabled or not speaking or not allowed:
            self.reset()
            return False
        if self.fired:
            return False
        try:
            speech = echo.is_user_speech(pcm, sample_rate, level)
        except Exception:
            speech = False
        if not speech:
            self.count, self.since = 0, None
            self._audio.clear()
            return False
        self._audio.append(pcm.tobytes())
        if self.since is None:
            self.since = now
        self.count += 1
        if self.count < max(2, echo.required_blocks):
            return False
        self.last_detection_ms = round((now - self.since) * 1000, 1)
        self.fired = True
        return True
