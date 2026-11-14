"""Deterministic hand-to-mouse state machine. No camera, Qt or model imports."""
import math


class PinchPointer:
    def __init__(self, mouse):
        self.mouse = mouse
        self.pressed = False
        self.armed = False
        self.open_since = None
        self.pinch_since = None
        self.position = None

    def release(self):
        if self.pressed:
            self.mouse.up()
            self.pressed = False

    def reset(self):
        self.release()
        self.armed = False
        self.open_since = self.pinch_since = self.position = None

    def update(self, points, now):
        if (len(points) != 21 or any(len(p) != 2 or any(
                not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1
                for v in p) for p in points)):
            self.reset()
            return 'Mão fora de vista · abra a pinça para retomar'
        span = math.dist(points[5], points[17])
        if span < .035:
            self.reset()
            return 'Aproxime a mão da câmera'
        ratio = math.dist(points[4], points[8]) / span
        # An open hand must be observed before the first grab and after tracking loss.
        if not self.armed:
            if ratio > .55:
                if self.open_since is None:
                    self.open_since = now
                self.armed = now - self.open_since >= .3
            else:
                self.open_since = None
            if not self.armed:
                return 'Abra a pinça por um instante para armar'
        width, height = self.mouse.size()
        # Mirror horizontal movement; central camera area spans the primary screen.
        x = max(8, min(width - 9, (1 - points[8][0] - .1) / .8 * width))
        y = max(8, min(height - 9, (points[8][1] - .1) / .8 * height))
        if self.position is None:
            self.position = (x, y)
        else:
            self.position = tuple(old + .35 * (new - old)
                                  for old, new in zip(self.position, (x, y)))
        self.mouse.move(*(round(v) for v in self.position))
        if ratio < .30:
            if self.pinch_since is None:
                self.pinch_since = now
            if not self.pressed and now - self.pinch_since >= .18:
                self.pressed = True  # Ensure cleanup attempts release even if down fails.
                self.mouse.down()
        elif ratio > .55:
            self.release()
            self.pinch_since = None
        elif not self.pressed:
            self.pinch_since = None
        return 'Pinça fechada · arrastando' if self.pressed else 'Indicador move · pinça segura'


class WindowsMouse:
    def __init__(self):
        import sys
        if sys.platform != 'win32':
            raise RuntimeError('Controle de gestos disponível somente no Windows')
        import ctypes
        self.api = ctypes.windll.user32

    def size(self):
        return self.api.GetSystemMetrics(0), self.api.GetSystemMetrics(1)

    def move(self, x, y):
        if not self.api.SetCursorPos(x, y):
            raise RuntimeError('Windows recusou mover o cursor')

    def down(self):
        self.api.mouse_event(0x0002, 0, 0, 0, 0)

    def up(self):
        self.api.mouse_event(0x0004, 0, 0, 0, 0)

    def emergency(self):
        return any(self.api.GetAsyncKeyState(key) & 0x8000 for key in (0x1B, 0x79))
