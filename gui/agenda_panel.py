"""Agenda dialog. All network/store work runs on workers; UI stays on Qt."""
import json
import threading
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton,
                             QCheckBox, QPlainTextEdit)
from gui.theme import C
from gui.style import hud_font
from memory.config_manager import get_plugin_config, save_plugin_config


class AgendaPanel(QDialog):
    finished_work = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Agenda / Schedule")
        self.resize(650, 560)
        self.setFont(hud_font(10))
        self.setStyleSheet(f"background:{C.BG};color:{C.TEXT};")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Configure a sua conta Trello nas configurações de plugins.\n"
                                "Set your own Trello account in plugin settings."))
        cfg = get_plugin_config("agenda")
        self.enabled = QCheckBox("Sincronizar com Trello a cada 60 s / Sync with Trello every 60 s")
        self.enabled.setChecked(bool(cfg.get("enabled")))
        layout.addWidget(self.enabled)
        self.list_id = QLineEdit(str(cfg.get("list_id") or ""))
        self.list_id.setPlaceholderText("ID da SUA lista Trello / YOUR Trello list ID")
        layout.addWidget(self.list_id)
        self.save_btn = QPushButton("Salvar configuração / Save settings")
        self.save_btn.clicked.connect(self._save)
        layout.addWidget(self.save_btn)
        self.display = QPlainTextEdit()
        self.display.setReadOnly(True)
        layout.addWidget(self.display)
        self.title = QLineEdit()
        self.title.setPlaceholderText("Título exato do evento / Exact event title")
        layout.addWidget(self.title)
        self.due = QLineEdit()
        self.due.setPlaceholderText("2026-11-14T17:00:00-03:00")
        layout.addWidget(self.due)
        self.buttons = [self.save_btn]
        for label, action in (("Atualizar lista / Refresh", "list"), ("Adicionar / Add", "add"),
                              ("Reagendar / Reschedule", "reschedule"), ("Sincronizar agora / Sync now", "sync")):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, a=action: self._execute(a))
            self.buttons.append(button)
            layout.addWidget(button)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.finished_work.connect(self._finish)
        self._execute("list")

    def _save(self):
        try:
            save_plugin_config("agenda", {"enabled": self.enabled.isChecked(),
                                         "list_id": self.list_id.text().strip()})
            self.status.setText("Configuração salva / Settings saved")
        except Exception:
            self.status.setText("Falha ao salvar / Save failed")

    def _execute(self, action):
        values = {"action": action, "title": self.title.text(), "due": self.due.text()}
        for button in self.buttons:
            button.setEnabled(False)
        self.status.setText("Processando / Working…")
        def work():
            try:
                from plugins.agenda import run
                from core.agenda_store import all_events
                result = run(values)
                events = json.dumps(all_events(), ensure_ascii=False, indent=2)
            except Exception:
                result, events = "Falha / Failure", ""
            try:
                self.finished_work.emit(result, events)
            except RuntimeError:
                pass  # Dialog was closed while the worker finished.
        threading.Thread(target=work, name="agenda-panel", daemon=True).start()

    def _finish(self, result, events):
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setText(result)
        self.display.setPlainText(events)
        for button in self.buttons:
            button.setEnabled(True)
