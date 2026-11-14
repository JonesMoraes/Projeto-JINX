"""Opt-in, local hand control using the app's single camera capture.

All inference/mouse work runs off Qt. A watchdog releases a held mouse button
when inference stalls or a global Windows Esc/F10 is pressed.
"""
from pathlib import Path
import queue
import struct
import subprocess
import threading
import time

from core.pinch_pointer import PinchPointer, WindowsMouse

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'config' / 'gesture_runtime'
PYTHON = RUNTIME / 'env' / 'Scripts' / 'python.exe'
MODEL = RUNTIME / 'hand_landmarker.task'


class GestureControl:
    def __init__(self):
        self.lock = threading.RLock()
        self.frames = queue.Queue(maxsize=1)
        self.stop_event = threading.Event()
        self.running = False
        self.process = None
        self.pointer = None
        self.notify = lambda text: None
        self.last_result = 0.0
        self.last_feed = 0.0
        self.state = 'Gestos desligados'

    def status(self):
        with self.lock:
            return {'active': self.running and not self.stop_event.is_set(), 'state': self.state}

    def report(self, message):
        if self.state != message:
            self.state = message
            try: self.notify(message)
            except Exception: pass

    def start(self, notify):
        with self.lock:
            if self.running:
                return False, 'Controle por gestos já iniciado'
            if not PYTHON.is_file() or not MODEL.is_file():
                return False, 'Instale o suporte em Configurações dos plugins → GESTOS / PINÇA.'
            self.pointer = PinchPointer(WindowsMouse())
            self.stop_event.clear()
            while not self.frames.empty():
                try: self.frames.get_nowait()
                except queue.Empty: break
            self.running = True
            self.notify = notify
            self.last_result = time.monotonic()
            self.report('Preparando gestos · Esc/F10 para parar')
            try:
                threading.Thread(target=self._run, daemon=True, name='hand-control').start()
            except Exception:
                self.running = False
                self.pointer = None
                raise
            return True, 'Preparando reconhecimento local; abra a mão para armar.'

    def stop(self):
        self.stop_event.set()
        while not self.frames.empty():
            try: self.frames.get_nowait()
            except queue.Empty: break
        with self.lock:
            if self.pointer:
                self.pointer.reset()
            proc = self.process
            self.report('Gestos desligados')
        if proc and proc.poll() is None:
            try: proc.terminate()
            except OSError: pass

    def feed(self, frame):
        if not self.running or self.stop_event.is_set():
            return
        now = time.monotonic()
        if now - self.last_feed < .08:
            return
        self.last_feed = now
        import cv2
        rgb = cv2.cvtColor(cv2.resize(frame, (480, 270)), cv2.COLOR_BGR2RGB)
        item = (now, rgb.tobytes())
        try: self.frames.put_nowait(item)
        except queue.Full:
            try: self.frames.get_nowait()
            except queue.Empty: pass
            try: self.frames.put_nowait(item)
            except queue.Full: pass

    def _watch(self):
        began = time.monotonic()
        while not self.stop_event.wait(.04):
            try:
                with self.lock:
                    if not self.running:
                        return
                    if self.pointer.mouse.emergency():
                        self.stop()
                        return
                    stale = time.monotonic() - self.last_result
                    if stale > .5:
                        self.pointer.reset()
                if stale > 3 and time.monotonic() - began > 20:
                    self.stop()
                    self.report('Gestos desligados · câmera/modelo sem resposta')
                    return
            except Exception:
                self.stop()
                return

    def _read(self, proc):
        import json
        line = proc.stdout.readline(16384)
        if not line or len(line) >= 16384:
            raise RuntimeError('Tracker unavailable')
        return json.loads(line)

    def _run(self):
        proc = None
        try:
            logs = ROOT / 'logs'
            logs.mkdir(exist_ok=True)
            with (logs / 'hand-tracker.log').open('ab') as log:
                proc = subprocess.Popen(
                    [str(PYTHON), '-I', '-u', str(ROOT / 'core' / '_hand_tracker.py'), str(MODEL)],
                    cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                with self.lock:
                    self.process = proc
                threading.Thread(target=self._watch, daemon=True, name='gesture-stop').start()
                if self.stop_event.is_set() or self._read(proc).get('ready') is not True:
                    return
                self.report('Abra a pinça para armar · Esc/F10 para parar')
                while not self.stop_event.is_set():
                    try: captured, data = self.frames.get(timeout=.1)
                    except queue.Empty: continue
                    if time.monotonic() - captured > .3:
                        continue
                    proc.stdin.write(struct.pack('<I', len(data)) + data)
                    proc.stdin.flush()
                    result = self._read(proc)
                    now = time.monotonic()
                    with self.lock:
                        if self.stop_event.is_set():
                            break
                        self.last_result = now
                        # Never apply a stale pinch after slow inference.
                        if now - captured > .4:
                            self.pointer.reset()
                            continue
                        self.report(self.pointer.update(result.get('points', []), now))
        except Exception as exc:
            if not self.stop_event.is_set():
                self.report('Gestos indisponíveis · ' + type(exc).__name__ + ' · confira logs/hand-tracker.log')
        finally:
            self.stop_event.set()
            with self.lock:
                if self.pointer:
                    self.pointer.reset()
                if proc and proc.poll() is None:
                    proc.terminate()
            if proc:
                try: proc.wait(timeout=3)
                except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=3)
                for stream in (proc.stdin, proc.stdout):
                    if stream: stream.close()
            with self.lock:
                self.process = None
                self.pointer = None
                self.running = False
                if self.state not in ('Gestos desligados',) and 'indisponíveis' not in self.state:
                    self.report('Gestos desligados')


control = GestureControl()
