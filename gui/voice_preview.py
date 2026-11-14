"""Qt-only voice picker with an independent listen button in every row."""
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QSize
from PyQt6.QtWidgets import QComboBox, QListView, QWidget, QHBoxLayout, QPushButton
from gui.style import hud_font, btn_css
from gui.theme import C
from core.voice_preview import PreviewPlayer


class VoicePicker(QComboBox):
    preview_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setView(QListView())
        self.setMaxVisibleItems(8)
        self.preview_buttons = {}

    def showPopup(self):
        for row in range(self.count()):
            idx = self.model().index(row, 0)
            self.model().setData(idx, QSize(300, 36), Qt.ItemDataRole.SizeHintRole)
            item = QWidget()
            item.setStyleSheet(f'background: {C.BG}; color: {C.TEXT};')
            layout = QHBoxLayout(item)
            layout.setContentsMargins(2, 0, 2, 0)
            choose = QPushButton(self.itemText(row))
            choose.setFont(hud_font(8))
            choose.setStyleSheet(btn_css('dim'))
            choose.setMinimumHeight(30)
            choose.clicked.connect(lambda checked=False, r=row: self._choose(r))
            play = QPushButton('▶')
            play.setFixedWidth(36)
            play.setStyleSheet(btn_css('choice', 'center'))
            play.setMinimumHeight(30)
            voice = self.itemData(row)
            play.setAccessibleName(f'Ouvir prévia da voz {voice}')
            play.setToolTip(f'Ouvir {voice} sem aplicar')
            play.clicked.connect(lambda checked=False, v=voice: self.preview_requested.emit(v))
            self.preview_buttons[voice] = play
            layout.addWidget(choose, 1)
            layout.addWidget(play)
            self.view().setIndexWidget(idx, item)
        super().showPopup()

    def _choose(self, row):
        self.setCurrentIndex(row)
        self.hidePopup()


class VoicePreviewController(QObject):
    status = pyqtSignal(str, str)

    def __init__(self, parent, activity):
        super().__init__(parent)
        self.player = PreviewPlayer(self.status.emit, activity)
