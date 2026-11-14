"""Cancelable voice samples. No settings writes and no Qt objects on workers."""
import threading
import re
from collections import OrderedDict

_play_lock = threading.Lock()


def sample_pcm(data, mime):
    from providers.audio import wav_to_pcm, resample
    if not data or len(data) > 2_000_000:
        raise ValueError('Invalid voice sample')
    if data.startswith(b'RIFF'):
        import io
        import wave
        with wave.open(io.BytesIO(data), 'rb') as sample:
            if not 8000 <= sample.getframerate() <= 48000 or sample.getnchannels() not in (1, 2):
                raise ValueError('Invalid WAV format')
        pcm = wav_to_pcm(data)
    elif 'l16' in mime.lower() or 'pcm' in mime.lower():
        match = re.search(r'rate=(\d+)', mime, re.I)
        rate = int(match.group(1)) if match else 24000
        if not 8000 <= rate <= 48000:
            raise ValueError('Invalid sample rate')
        pcm = resample(data[:len(data) // 2 * 2], rate, 24000)
    else:
        raise ValueError('Unsupported audio format')
    if not pcm:
        raise ValueError('Empty voice sample')
    return pcm[:24000 * 2 * 8]


class PreviewPlayer:
    def __init__(self, notify, activity=None):
        self.notify = notify
        self.activity = activity
        self._lock = threading.Lock()
        self._pending = None
        self._worker = None
        self._cancel = threading.Event()
        self._cache = OrderedDict()

    def request(self, voice):
        with self._lock:
            self._cancel.set()
            self._pending = voice
            if self._worker is None:
                self._worker = threading.Thread(target=self._run, daemon=True)
                self._worker.start()

    def stop(self):
        with self._lock:
            self._pending = None
            self._cancel.set()

    def _emit(self, voice, message):
        try:
            self.notify(voice, message)
        except RuntimeError:  # overlay destroyed while a request was in flight
            pass

    def _run(self):
        from core import gemini
        while True:
            with self._lock:
                voice = self._pending
                self._pending = None
                if voice is None:
                    self._worker = None
                    return
                cancel = self._cancel = threading.Event()
            try:
                self._emit(voice, 'Gerando amostra…')
                pcm = self._cache.get(voice)
                if pcm is None:
                    result = gemini.preview_voice(voice, cancel)
                    if cancel.is_set():
                        continue
                    if result is None:
                        raise RuntimeError('Amostra indisponível')
                    pcm = sample_pcm(*result)
                    self._cache[voice] = pcm
                    if len(self._cache) > 8:
                        self._cache.popitem(last=False)
                else:
                    self._cache.move_to_end(voice)
                while not cancel.is_set():
                    if _play_lock.acquire(timeout=.1):
                        try:
                            self._play(voice, pcm, cancel)
                        finally:
                            _play_lock.release()
                        break
                if not cancel.is_set():
                    self._emit(voice, 'Prévia concluída. Aplicar confirma a voz.')
            except Exception as exc:
                print(f'[Voice preview] {type(exc).__name__}')
                if not cancel.is_set():
                    self._emit(voice, 'Não foi possível ouvir. Verifique a conta Gemini e a saída de áudio.')

    def _play(self, voice, pcm, cancel):
        import sounddevice as sd
        from core import audio_devices
        from memory.config_manager import get_output_device
        stream = None
        active = False
        try:
            device = audio_devices.resolve(get_output_device(), 'output')
            if cancel.is_set():
                return
            if self.activity:
                active = True
                delay = self.activity(True) or 0
                if cancel.wait(delay):
                    return
            stream = sd.RawOutputStream(samplerate=24000, channels=1, dtype='int16', device=device)
            stream.start()
            self._emit(voice, 'Reproduzindo…')
            for offset in range(0, len(pcm), 2400):
                if cancel.is_set():
                    break
                stream.write(pcm[offset:offset + 2400])
        finally:
            try:
                if stream is not None:
                    try:
                        if cancel.is_set(): stream.abort()
                        else: stream.stop()
                    finally:
                        stream.close()
            finally:
                if active:
                    self.activity(False)
