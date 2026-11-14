"""gui/reactor.py — voice-reactive neural particle orb for the JINX HUD.

The orb is projected as a small 3-D point cloud: a triangulated luminous
surface, drifting particles and branching filaments. It stays on the existing
QPainter path, so it needs no browser, GPU or additional package. The HUD feeds
the same smoothed microphone and speech level used by the waveform.
"""
from __future__ import annotations

import math

import numpy as np
from PyQt6.QtCore import QLineF, QPointF, Qt
from PyQt6.QtGui import (QBrush, QColor, QImage, QPainter, QPen, QPixmap,
                         QPolygonF, QRadialGradient)

_CAM_D = 4.0


def _rx(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])


def _ry(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


def _rz(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def _with_alpha(col: QColor, alpha: float) -> QColor:
    result = QColor(col)
    result.setAlphaF(max(0.0, min(1.0, alpha)))
    return result


def _unit(v: np.ndarray) -> np.ndarray:
    return v / max(1e-9, float(np.linalg.norm(v)))


class Reactor3D:
    """State and software renderer for JINX's voice-reactive orb."""

    # The HUD sizes the orb from this total vertical extent.
    TOP = 1.31
    BOTTOM = 1.31
    _SPRITE_SIZE = 512
    _SPRITE_RADIUS = 240.0

    def __init__(self):
        rng = np.random.default_rng(4217)

        # Evenly spaced points keep the shell detailed at every window size.
        count = 440
        i = np.arange(count, dtype=np.float64)
        y = 1.0 - 2.0 * (i + 0.5) / count
        radius = np.sqrt(1.0 - y * y)
        angle = math.pi * (3.0 - math.sqrt(5.0)) * i
        self._surface = np.vstack((radius * np.cos(angle), y,
                                   radius * np.sin(angle)))
        self._surface_phase = rng.uniform(0.0, math.tau, count)

        # Connect each shell point to nearby neighbours, then add longer
        # cross-links so the surface reads as a tangled neural network.
        delta = self._surface.T[:, None, :] - self._surface.T[None, :, :]
        distance = np.einsum("ijk,ijk->ij", delta, delta)
        nearest = np.argpartition(distance, 5, axis=1)[:, 1:5]
        edges = {tuple(sorted((int(a), int(b))))
                 for a in range(count) for b in nearest[a]}
        for _ in range(210):
            a, b = rng.integers(0, count, size=2)
            if a != b:
                edges.add(tuple(sorted((int(a), int(b)))))
        edge_array = np.asarray(sorted(edges), dtype=np.int32)
        self._edge_a, self._edge_b = edge_array[:, 0], edge_array[:, 1]

        # Fine-grain particles are biased toward the surface, with a second
        # layer inside it. They shimmer and breathe with the live audio level.
        particle_count = 5200
        directions = rng.normal(size=(particle_count, 3))
        directions /= np.maximum(1e-9, np.linalg.norm(directions, axis=1))[:, None]
        radii = 0.40 + 0.72 * rng.random(particle_count) ** 0.28
        self._cloud = (directions * radii[:, None]).T
        self._cloud_phase = rng.uniform(0.0, math.tau, particle_count)
        self._cloud_glint = rng.random(particle_count)
        self._cloud_tint = rng.random(particle_count)
        self._hot = np.argsort(self._cloud_glint)[-48:]

        # Curved paths on the shell create the branching, electric filaments.
        segments = []

        def grow(position, tangent, steps, path_radius):
            for _ in range(steps):
                drift = rng.normal(size=3) * 0.31
                direction = tangent + drift
                tangent = _unit(direction - position * np.dot(direction, position))
                next_position = _unit(position + tangent * float(rng.uniform(0.075, 0.16)))
                segments.append((position * path_radius, next_position * path_radius))
                position = next_position
            return position, tangent

        for _ in range(54):
            position = _unit(rng.normal(size=3))
            tangent = rng.normal(size=3)
            tangent = _unit(tangent - position * np.dot(tangent, position))
            path_radius = float(rng.uniform(0.80, 0.97))
            steps = int(rng.integers(10, 16))
            for step in range(steps):
                position, tangent = grow(position, tangent, 1, path_radius)
                if step in (2, 5, 8, 11) and rng.random() < 0.76:
                    branch_direction = tangent + rng.normal(size=3) * 0.82
                    branch_tangent = _unit(
                        branch_direction - position * np.dot(branch_direction, position))
                    grow(position.copy(), branch_tangent,
                         int(rng.integers(3, 7)),
                         path_radius * float(rng.uniform(0.97, 1.035)))

        segment_array = np.asarray(segments, dtype=np.float64)
        self._filament_a = segment_array[:, 0, :].T
        self._filament_b = segment_array[:, 1, :].T

        self.spin = 0.0
        self.phase = 0.0
        self.muted = False
        self._view = _rx(math.radians(11.0))
        self._sprite_key = None
        self._sprite: QPixmap | None = None

    def step(self, dt: float, speaking: bool, thinking: bool, muted: bool) -> None:
        dt = min(0.10, max(0.0, dt))
        rate = 0.10 if muted else 0.28 + (0.80 if thinking else 0.0) + (0.65 if speaking else 0.0)
        self.spin += dt * rate
        self.phase += dt * (0.8 + (1.8 if speaking else 0.0))
        self.muted = muted

    def _project(self, points: np.ndarray, cx: float, cy: float, scale: float):
        view = self._view @ points
        depth_scale = _CAM_D / np.maximum(0.5, _CAM_D - view[2])
        return (cx + view[0] * depth_scale * scale,
                cy - view[1] * depth_scale * scale,
                view[2], depth_scale)

    @staticmethod
    def _lines(p: QPainter, x1, y1, x2, y2, depth, front: bool,
               colour: QColor, alpha: float, width: float) -> None:
        mask = depth >= 0.0 if front else depth < 0.0
        indices = np.flatnonzero(mask)
        if not len(indices):
            return
        lines = [QLineF(float(x1[n]), float(y1[n]), float(x2[n]), float(y2[n]))
                 for n in indices]
        pen = QPen(_with_alpha(colour, alpha if front else alpha * 0.26), width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLines(lines)

    @staticmethod
    def _points(p: QPainter, x, y, depth, mask, colour: QColor,
                alpha: float, size: float, front: bool = True) -> None:
        side = depth >= 0.0 if front else depth < 0.0
        visible = np.flatnonzero(mask & side)
        if len(visible):
            polygon = QPolygonF([QPointF(float(x[n]), float(y[n])) for n in visible])
            pen = QPen(_with_alpha(colour, alpha), size)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawPoints(polygon)

    def paint(self, p: QPainter, cx: float, cy: float, r: float,
              main: QColor, acc: QColor, white: QColor, amp: float,
              live: bool, name: str = "") -> None:
        """Blit a cached high-detail orb and animate it cheaply per frame."""
        palette_key = (main.rgba(), white.rgba(), self.muted)
        if self._sprite is None or self._sprite_key != palette_key:
            image = QImage(self._SPRITE_SIZE, self._SPRITE_SIZE,
                           QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(Qt.GlobalColor.transparent)
            renderer = QPainter(image)
            renderer.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._paint_geometry(
                renderer, self._SPRITE_SIZE / 2, self._SPRITE_SIZE / 2,
                self._SPRITE_RADIUS, main, acc, white, 0.0, False, name)
            renderer.end()
            self._sprite = QPixmap.fromImage(image)
            self._sprite_key = palette_key

        amp = max(0.0, min(1.0, amp))
        voice = min(1.0, math.sqrt(amp * 3.0)) if live and not self.muted else 0.0
        radius_scale = (r / self._SPRITE_RADIUS) * (1.0 + 0.23 * voice)
        breathe = 1.0 + 0.008 * math.sin(self.phase * 1.7)
        radius_scale *= breathe
        halo_r = r * (1.08 + 0.23 * voice)

        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)

        # Audio-responsive bloom behind the cached details.
        halo_colour = QColor(main)
        halo = QRadialGradient(QPointF(cx, cy), halo_r)
        halo.setColorAt(0.0, _with_alpha(halo_colour, 0.12 + 0.20 * voice))
        halo.setColorAt(0.48, _with_alpha(halo_colour, 0.08 + 0.11 * voice))
        halo.setColorAt(1.0, _with_alpha(halo_colour, 0.0))
        p.setBrush(QBrush(halo))
        p.drawEllipse(QPointF(cx, cy), halo_r, halo_r)

        # A slight squash/turn keeps the cached hologram moving without
        # rebuilding thousands of particle and line objects every frame.
        p.save()
        p.translate(cx, cy)
        p.rotate(math.degrees(self.spin * 0.13))
        tilt = 0.985 + 0.015 * math.sin(self.phase * 0.42)
        p.scale(radius_scale, radius_scale * tilt)
        p.drawPixmap(-self._SPRITE_SIZE // 2, -self._SPRITE_SIZE // 2, self._sprite)
        p.restore()

        # The heart is redrawn live, so even short sounds visibly swell at once.
        if voice > 0.015:
            nucleus_r = 18.0 + 42.0 * voice
            nucleus = QRadialGradient(QPointF(cx, cy), nucleus_r)
            nucleus.setColorAt(0.0, _with_alpha(QColor(220, 250, 255), 0.32 + 0.50 * voice))
            nucleus.setColorAt(0.22, _with_alpha(halo_colour, 0.42 + 0.42 * voice))
            nucleus.setColorAt(1.0, _with_alpha(halo_colour, 0.0))
            p.setBrush(QBrush(nucleus))
            p.drawEllipse(QPointF(cx, cy), nucleus_r, nucleus_r)
        p.restore()

    def _paint_geometry(self, p: QPainter, cx: float, cy: float, r: float,
                        main: QColor, acc: QColor, white: QColor, amp: float,
                        live: bool, name: str = "") -> None:
        del acc, name  # the orb keeps its cyan/violet palette; HUD shows state separately
        amp = max(0.0, min(1.0, amp))
        muted = self.muted
        cyan = QColor(main)
        blue = QColor(42, 145, 255)
        violet = QColor(158, 89, 255)
        core_white = QColor(white) if not muted else QColor(main)
        pulse = math.sin(self.phase * 1.7)
        breath = 1.0 + 0.012 * pulse + (0.075 * amp if live else 0.0)
        sphere_r = r * 0.91
        rotation = (_ry(self.spin * 0.72)
                    @ _rz(0.08 * math.sin(self.phase * 0.35))
                    @ _rx(0.11 * math.sin(self.phase * 0.27)))

        # Gently deform the shell and the floating particles in step with speech.
        surface_wave = (1.0 + 0.013 * np.sin(self._surface_phase + self.phase * 1.5)
                        + (0.018 + amp * 0.027) * np.sin(self._surface_phase * 2.1 - self.phase * 8.0))
        shell = self._surface * (surface_wave * breath * 0.91)
        shell = rotation @ shell
        sx, sy, sz, _ = self._project(shell, cx, cy, sphere_r)

        cloud_wave = 1.0 + (0.012 * np.sin(self._cloud_phase + self.phase * 1.3)
                            + (0.025 * amp if live else 0.0))
        cloud = rotation @ (self._cloud * cloud_wave)
        px, py, pz, _ = self._project(cloud, cx, cy, sphere_r)

        edge_x1, edge_y1 = sx[self._edge_a], sy[self._edge_a]
        edge_x2, edge_y2 = sx[self._edge_b], sy[self._edge_b]
        edge_depth = (sz[self._edge_a] + sz[self._edge_b]) * 0.5

        fa = rotation @ (self._filament_a * breath)
        fb = rotation @ (self._filament_b * breath)
        fx1, fy1, fz1, _ = self._project(fa, cx, cy, sphere_r)
        fx2, fy2, fz2, _ = self._project(fb, cx, cy, sphere_r)
        filament_depth = (fz1 + fz2) * 0.5

        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)

        # Broad atmospheric halo behind the sphere.
        halo_r = sphere_r * (1.16 + 0.09 * amp)
        halo = QRadialGradient(QPointF(cx, cy), halo_r)
        halo.setColorAt(0.00, _with_alpha(blue, 0.28 + 0.16 * amp))
        halo.setColorAt(0.43, _with_alpha(violet, 0.16 + 0.07 * amp))
        halo.setColorAt(0.76, _with_alpha(cyan, 0.055))
        halo.setColorAt(1.00, _with_alpha(cyan, 0.0))
        p.setBrush(QBrush(halo))
        p.drawEllipse(QPointF(cx, cy), halo_r, halo_r)

        # The far side of the network recedes into the light, then the luminous
        # core gives the points depth instead of making the orb look flat.
        self._lines(p, edge_x1, edge_y1, edge_x2, edge_y2, edge_depth,
                    False, cyan, 0.17, 0.60)
        self._lines(p, fx1, fy1, fx2, fy2, filament_depth,
                    False, violet, 0.34, 1.1)

        back = pz < 0.0
        self._points(p, px, py, pz, back & (self._cloud_glint < 0.72), blue, 0.32, 1.0, front=False)
        self._points(p, px, py, pz, back & (self._cloud_glint >= 0.72), violet, 0.36, 1.2, front=False)

        core_r = sphere_r * (0.77 + 0.018 * amp)
        core = QRadialGradient(QPointF(cx - core_r * 0.12, cy - core_r * 0.16),
                               core_r, QPointF(cx, cy))
        core.setColorAt(0.00, _with_alpha(core_white, 0.65 + 0.30 * amp))
        core.setColorAt(0.18, _with_alpha(cyan, 0.43 + 0.24 * amp))
        core.setColorAt(0.52, _with_alpha(blue, 0.22 + 0.12 * amp))
        core.setColorAt(0.82, _with_alpha(violet, 0.055))
        core.setColorAt(1.00, _with_alpha(cyan, 0.0))
        p.setBrush(QBrush(core))
        p.drawEllipse(QPointF(cx, cy), core_r, core_r)

        nucleus_r = 24.0 + 16.0 * amp
        nucleus = QRadialGradient(QPointF(cx, cy), nucleus_r)
        nucleus.setColorAt(0.00, _with_alpha(core_white, 0.98))
        nucleus.setColorAt(0.20, _with_alpha(QColor(126, 232, 255), 0.92))
        nucleus.setColorAt(0.58, _with_alpha(blue, 0.30 + amp * 0.24))
        nucleus.setColorAt(1.00, _with_alpha(cyan, 0.0))
        p.setBrush(QBrush(nucleus))
        p.drawEllipse(QPointF(cx, cy), nucleus_r, nucleus_r)

        # Dense particle cloud, split into tiny grains and brighter sparks.
        front = pz >= 0.0
        glint = self._cloud_glint
        tint = self._cloud_tint
        self._points(p, px, py, pz, front & (glint < 0.50) & (tint < 0.80),
                     cyan, 0.52 + amp * 0.18, 1.25)
        self._points(p, px, py, pz, front & (glint < 0.50) & (tint >= 0.80),
                     violet, 0.49 + amp * 0.16, 1.35)
        self._points(p, px, py, pz, front & (glint >= 0.50) & (glint < 0.84),
                     blue, 0.73 + amp * 0.20, 1.75)
        self._points(p, px, py, pz, front & (glint >= 0.84),
                     core_white, 0.86 + amp * 0.12, 2.0)
        self._points(p, sx, sy, sz, sz >= 0.0, cyan, 0.90, 1.6)

        # Front-facing electric filaments and graph lines catch more light.
        self._lines(p, fx1, fy1, fx2, fy2, filament_depth,
                    True, violet, 0.52 + amp * 0.18, 2.2)
        self._lines(p, fx1, fy1, fx2, fy2, filament_depth,
                    True, cyan, 0.72 + amp * 0.20, 0.90)
        self._lines(p, edge_x1, edge_y1, edge_x2, edge_y2, edge_depth,
                    True, blue, 0.14 + amp * 0.06, 0.58)
        self._lines(p, edge_x1, edge_y1, edge_x2, edge_y2, edge_depth,
                    True, cyan, 0.18 + amp * 0.12, 0.44)

        # A few hot nodes read as individual sparks; their glow grows with voice.
        for n in self._hot:
            if pz[n] < 0.0:
                continue
            x, y = float(px[n]), float(py[n])
            glow_r = 2.1 + 2.5 * float(self._cloud_glint[n]) + 2.8 * amp
            colour = violet if self._cloud_tint[n] > 0.76 else blue
            glow = QRadialGradient(QPointF(x, y), glow_r)
            glow.setColorAt(0.0, _with_alpha(core_white, 0.94))
            glow.setColorAt(0.24, _with_alpha(colour, 0.68))
            glow.setColorAt(1.0, _with_alpha(colour, 0.0))
            p.setBrush(QBrush(glow))
            p.drawEllipse(QPointF(x, y), glow_r, glow_r)

        # Thin optical rim makes the spherical silhouette legible through the
        # particles without adding a hard solid outline.
        rim = QRadialGradient(QPointF(cx, cy), sphere_r)
        rim.setColorAt(0.70, _with_alpha(cyan, 0.0))
        rim.setColorAt(0.91, _with_alpha(cyan, 0.015 + amp * 0.015))
        rim.setColorAt(0.985, _with_alpha(core_white, 0.12 + amp * 0.12))
        rim.setColorAt(1.00, _with_alpha(blue, 0.04))
        p.setBrush(QBrush(rim))
        p.drawEllipse(QPointF(cx, cy), sphere_r, sphere_r)

        p.restore()
