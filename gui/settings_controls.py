"""Compact native setting controls; checked state stays accessible to Qt."""
from PyQt6.QtCore import Qt, QRectF, QSize
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from gui.theme import C
from gui.style import hud_font


class ToggleSwitch(QCheckBox):
    """Keyboard-accessible two-state switch with a full rectangular hit area."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('SettingsSwitch')
        self.setFixedSize(48, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.toggled.connect(self.update)

    def sizeHint(self):
        return QSize(48, 28)

    def hitButton(self, point):
        return self.rect().contains(point)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.4)
        accent = self.property('switchAccent') or C.PRI
        border = self.property('switchBorder') or C.BORDER_B
        track = self.property('switchTrack') or C.PANEL2
        p.setPen(QPen(QColor(accent if self.isChecked() else border), 1))
        p.setBrush(QColor(accent if self.isChecked() else track))
        p.drawRoundedRect(QRectF(2, 4, 44, 20), 10, 10)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self.property('switchKnob') or C.WHITE))
        p.drawEllipse(QRectF(28 if self.isChecked() else 6, 7, 14, 14))
        if self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(accent), 1, Qt.PenStyle.DotLine))
            p.drawRoundedRect(QRectF(0.5, 0.5, 47, 27), 13, 13)


class ToggleRow(QWidget):
    """Label and optional help on the left, state and switch on the right."""
    def __init__(self, title, description='', parent=None):
        super().__init__(parent)
        self.setObjectName('SettingsToggleRow')
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 7, 0, 7)
        row.setSpacing(12)
        copy = QVBoxLayout()
        copy.setSpacing(3)
        self.label = QLabel(title)
        self.label.setWordWrap(True)
        self.label.setFont(hud_font(9))
        copy.addWidget(self.label)
        if description:
            help_text = QLabel(description)
            help_text.setObjectName('SettingsHint')
            help_text.setWordWrap(True)
            help_text.setFont(hud_font(8))
            copy.addWidget(help_text)
        row.addLayout(copy, 1)
        self.state = QLabel('Desligado')
        self.state.setObjectName('SettingsHint')
        self.state.setFont(hud_font(8))
        self.state.setMinimumWidth(64)
        row.addWidget(self.state)
        self.switch = ToggleSwitch()
        self.switch.setAccessibleName(title)
        self.switch.setAccessibleDescription(description)
        self.label.setBuddy(self.switch)
        row.addWidget(self.switch)
        self.switch.toggled.connect(lambda on: self.state.setText('Ligado' if on else 'Desligado'))
