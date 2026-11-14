"""Small Qt-painted local air/airport radar; no WebEngine or map tiles."""
import math
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout
from gui.theme import C
from gui.style import hud_font, btn_css


class RadarCanvas(QWidget):
    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.data = data
        self.setMinimumSize(420, 400)

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height(); center = (w / 2, h / 2)
        radius = min(w, h) * .43
        p.fillRect(self.rect(), QColor(C.BG))
        p.setPen(QPen(QColor(C.BORDER), 1))
        for ratio in (.25, .5, .75, 1):
            p.drawEllipse(QRectF(center[0]-radius*ratio, center[1]-radius*ratio,
                                 2*radius*ratio, 2*radius*ratio))
        p.drawLine(int(center[0]-radius), int(center[1]), int(center[0]+radius), int(center[1]))
        p.drawLine(int(center[0]), int(center[1]-radius), int(center[0]), int(center[1]+radius))
        p.setPen(QPen(QColor(C.PRI), 1)); p.setBrush(QColor(C.PRI))
        p.drawEllipse(int(center[0]-4), int(center[1]-4), 8, 8)
        lat0 = float(self.data.get("center", {}).get("lat", 0))
        lon0 = float(self.data.get("center", {}).get("lon", 0))
        extent = float(self.data.get("radius_km", 25))
        cosine = max(.1, math.cos(math.radians(lat0)))
        def point(lat, lon):
            east = (lon-lon0) * 111.32 * cosine
            north = (lat-lat0) * 110.57
            return center[0]+east/extent*radius, center[1]-north/extent*radius
        for airport in self.data.get("airports", []):
            x, y = point(float(airport["lat"]), float(airport["lon"]))
            if abs(x-center[0]) <= radius and abs(y-center[1]) <= radius:
                p.setPen(QPen(QColor(C.ACC2), 1)); p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(int(x-4), int(y-4), 8, 8)
                p.setFont(hud_font(6)); p.drawText(int(x+6), int(y-4), str(airport.get("name", "Aerodrome"))[:18])
        for plane in self.data.get("planes", []):
            x, y = point(float(plane["lat"]), float(plane["lon"]))
            if abs(x-center[0]) <= radius and abs(y-center[1]) <= radius:
                p.setPen(QPen(QColor(C.GREEN), 2)); p.setBrush(QColor(C.GREEN))
                p.drawEllipse(int(x-4), int(y-4), 8, 8)
                p.setFont(hud_font(6)); p.drawText(int(x+6), int(y+12), str(plane.get("callsign") or "Aircraft")[:12])
        p.end()


class RadarWidget(QWidget):
    def __init__(self, data, on_close, parent=None):
        super().__init__(parent)
        self.data = data
        self.setFixedSize(460, 520)
        self.setStyleSheet(f"background:{C.BG}; border:1px solid {C.BORDER_B};")
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        title = QLabel("GLOBO / RADAR LOCAL")
        title.setFont(hud_font(11)); title.setStyleSheet(f"color:{C.PRI}; border:0")
        close = QPushButton("FECHAR"); close.setStyleSheet(btn_css("dim")); close.clicked.connect(on_close)
        header.addWidget(title); header.addStretch(); header.addWidget(close); layout.addLayout(header)
        layout.addWidget(RadarCanvas(data), 1)
        c = data.get("center", {})
        info = QLabel(f"Centro {c.get('lat',0):.3f}, {c.get('lon',0):.3f} · raio {data.get('radius_km')} km\n"
                      f"Aeronaves: {len(data.get('planes',[]))} · aeródromos: {len(data.get('airports',[]))}\n"
                      f"Atualizado: {data.get('fetched_at','—')} · fontes: {', '.join(data.get('sources',[]))}")
        info.setWordWrap(True); info.setFont(hud_font(7)); info.setStyleSheet(f"color:{C.TEXT_DIM}; border:0")
        layout.addWidget(info)
