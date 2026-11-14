"""Bounded asynchronous plugin jobs with a retrievable result and HUD delivery."""
import threading
from core import outcome


class Jobs:
    def __init__(self, title):
        self.title = title
        self.lock = threading.Lock()
        self.last = 'Sem operação / No operation'

    def notify(self, player, result):
        self.last = str(result)
        for method, args in (
            ('show_content', (self.title, outcome.unwrap(self.last))),
            ('request_say', ('Report this result briefly; do not call tools. ' + self.last,)),
        ):
            try:
                callback = getattr(player, method, None)
                if callable(callback):
                    callback(*args)
            except Exception:
                pass
        return self.last

    def start(self, work, player=None):
        if not self.lock.acquire(blocking=False):
            return outcome.unverified(self.title, 'Operação em andamento / Operation in progress')
        def worker():
            try:
                self.notify(player, work())
            except Exception:
                self.notify(player, outcome.unverified(self.title,
                    'Operação não verificada; confira configuração e conexão / Unverified; check settings and connection'))
            finally:
                self.lock.release()
        try:
            self.last = outcome.started(self.title)
            threading.Thread(target=worker, daemon=True, name='plugin-' + self.title).start()
        except Exception:
            self.lock.release()
            return outcome.failed(self.title, 'Não foi possível iniciar / Could not start')
        return outcome.started(self.title)
