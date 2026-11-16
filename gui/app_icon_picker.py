"""Qt-thread-only icon gallery and live application/window icon refresh."""
from pathlib import Path
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QLabel, QListWidget, QListWidgetItem, QListView, QPushButton, QVBoxLayout, QWidget
from core import app_icons


def apply_window_icon(window):
    icon = QIcon(str(app_icons.selected_path()))
    if icon.isNull():
        raise ValueError('Não foi possível carregar o ícone selecionado.')
    app = QApplication.instance()
    if app:
        app.setWindowIcon(icon)
        for widget in app.topLevelWidgets():
            widget.setWindowIcon(icon)
    window.setWindowIcon(icon)


class AppIconPicker(QWidget):
    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        hint = QLabel('Escolha um modelo e aplique à janela e aos atalhos existentes da JINX.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.gallery = QListWidget()
        self.gallery.setObjectName('AppIconGallery')
        self.gallery.setAccessibleName('Escolher ícone da JINX')
        self.gallery.setViewMode(QListView.ViewMode.IconMode)
        self.gallery.setResizeMode(QListView.ResizeMode.Adjust)
        self.gallery.setMovement(QListView.Movement.Static)
        self.gallery.setWrapping(True)
        self.gallery.setWordWrap(True)
        self.gallery.setIconSize(QSize(64, 64))
        self.gallery.setGridSize(QSize(144, 112))
        self.gallery.setFixedHeight(254)
        self.gallery.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.gallery.setMinimumWidth(0)
        chosen = app_icons.selected_id()
        for row in app_icons.available_icons():
            item = QListWidgetItem(QIcon(str(row['path'])), row['label'])
            item.setData(Qt.ItemDataRole.UserRole, row['id'])
            item.setToolTip(row['label'])
            self.gallery.addItem(item)
            if row['id'] == chosen:
                self.gallery.setCurrentItem(item)
        layout.addWidget(self.gallery)
        self.apply_button = QPushButton('Aplicar ícone')
        self.apply_button.setFixedHeight(32)
        self.apply_button.clicked.connect(self.apply)
        layout.addWidget(self.apply_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self.status = QLabel('A escolha só é salva ao clicar em Aplicar ícone.')
        self.status.setObjectName('SettingsHint')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

    def apply(self):
        item = self.gallery.currentItem()
        if item is None:
            return
        try:
            key = item.data(Qt.ItemDataRole.UserRole)
            path = app_icons.icon_path(key)
            if QIcon(str(path)).isNull():
                raise ValueError('O ícone não pôde ser carregado.')
            app_icons.select(key)
            apply_window_icon(self.window)
        except (ValueError, OSError) as exc:
            self.status.setText(str(exc))
            return
        try:
            desktop = self.window._get_desktop_dir() if hasattr(self.window, '_get_desktop_dir') else Path.home() / 'Desktop'
            result = app_icons.update_shortcuts(desktop)
            if result['failed']:
                self.status.setText('Ícone aplicado à JINX. Não foi possível atualizar: ' + ', '.join(result['failed']))
            else:
                self.status.setText(f"Ícone aplicado: {item.text()}. Atalhos atualizados: {len(result['updated'])}.")
        except Exception:
            self.status.setText('Ícone aplicado à JINX. Use Criar atalho na seção Sistema para atualizar o atalho.')
