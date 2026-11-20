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
        from PyQt6.QtWidgets import QLabel
        for row in range(self.count()):
            idx = self.model().index(row, 0)
            voice = self.itemData(row)
            theme = getattr(self, 'preview_theme', None)
            if not voice:
                # Group header ("VOZES FEMININAS" / "VOZES MASCULINAS"):
                # disabled in the model, so keyboard and click selection
                # can never land on it; rendered as an accent label.
                self.model().setData(idx, QSize(300, 24), Qt.ItemDataRole.SizeHintRole)
                model_item = self.model().item(row)
                if model_item is not None:
                    model_item.setEnabled(False)
                header = QWidget()
                header.setStyleSheet(
                    f'background: {theme.panel if theme is not None else C.BG};')
                header_layout = QHBoxLayout(header)
                header_layout.setContentsMargins(8, 2, 2, 2)
                label = QLabel(self.itemText(row))
                label.setFont(hud_font(8))
                accent = theme.accent if theme is not None else C.PRI
                label.setStyleSheet(
                    f'color: {accent}; background: transparent; letter-spacing: 1px;')
                header_layout.addWidget(label)
                header_layout.addStretch(1)
                self.view().setIndexWidget(idx, header)
                continue
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
            theme = getattr(self, 'preview_theme', None)
            if theme is not None:
                item.setStyleSheet(f'background: {theme.panel}; color: {theme.text};')
                for button in (choose, play):
                    button.setStyleSheet(
                        f'QPushButton {{background: {theme.panel}; color: {theme.text}; '
                        f'border: 1px solid {theme.border}; border-radius: {theme.radius}px; padding: 4px;}}'
                        f'QPushButton:hover {{background: {theme.selected}; color: {theme.accent};}}')
            self.preview_buttons[voice] = play
            layout.addWidget(choose, 1)
            layout.addWidget(play)
            self.view().setIndexWidget(idx, item)
        super().showPopup()

    def _choose(self, row):
        if self.itemData(row) is None:
            return  # Never select a group header.
        self.setCurrentIndex(row)
        self.hidePopup()


def fill_voice_picker(combo, selected=None):
    """Populate a VoicePicker grouped into feminine and masculine sections.

    Section headers are added with ``None`` as their data; VoicePicker renders
    them as accent labels and refuses to select them.
    """
    from memory.config_manager import VOICE_STYLES, voices_by_gender
    feminine, masculine = voices_by_gender()
    combo.addItem('VOZES FEMININAS', None)
    for name in feminine:
        combo.addItem(f'{name} — {VOICE_STYLES[name]}', name)
    combo.addItem('VOZES MASCULINAS', None)
    for name in masculine:
        combo.addItem(f'{name} — {VOICE_STYLES[name]}', name)
    if selected:
        combo.setCurrentIndex(max(0, combo.findData(selected)))


class VoicePreviewController(QObject):
    status = pyqtSignal(str, str)

    def __init__(self, parent, activity):
        super().__init__(parent)
        self.player = PreviewPlayer(self.status.emit, activity)
