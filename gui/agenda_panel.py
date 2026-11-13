"""Agenda dialog. All network/store work runs on workers; UI stays on Qt."""
import json
import threading
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QCheckBox, QComboBox, QTableWidget, QTableWidgetItem, QAbstractItemView)
from gui.theme import C
from gui.style import hud_font
from memory.config_manager import get_plugin_config, save_plugin_config


class AgendaPanel(QDialog):
    finished_work = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Agenda / Schedule")
        self.resize(720, 680)
        self.setFont(hud_font(10))
        self.setStyleSheet(f"background:{C.BG};color:{C.TEXT};")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Tarefas e eventos locais sem conta. Trello opcional nas configurações de plugins.\n"
                                "Local tasks and events need no account. Trello is optional in plugin settings."))
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
        self.kind = QComboBox()
        self.kind.addItem("Tarefas / Tasks", "task")
        self.kind.addItem("Eventos / Events", "event")
        layout.addWidget(self.kind)
        self.filter = QComboBox()
        for label, value in (("Abertos / Open", "open"), ("Hoje / Today", "today"),
                             ("Amanhã / Tomorrow", "tomorrow"), ("Atrasados / Overdue", "overdue"),
                             ("Concluídos / Done", "done"), ("Todos / All", "all")):
            self.filter.addItem(label, value)
        layout.addWidget(self.filter)
        self.display = QTableWidget(0, 4)
        self.display.setHorizontalHeaderLabels(["Título / Title", "Data / Date", "Estado / Status", "Prioridade / Priority"])
        self.display.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.display.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.display.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.display.itemSelectionChanged.connect(self._select)
        self.rows = []
        self.selected_id = None
        layout.addWidget(self.display)
        self.title = QLineEdit()
        self.title.setPlaceholderText("Título exato do evento / Exact event title")
        layout.addWidget(self.title)
        self.due = QLineEdit()
        self.due.setPlaceholderText("2026-11-14T17:00:00-03:00")
        layout.addWidget(self.due)
        self.priority = QComboBox()
        for label, value in (("Baixa / Low", "low"), ("Normal", "normal"), ("Alta / High", "high")):
            self.priority.addItem(label, value)
        self.priority.setCurrentIndex(1)
        layout.addWidget(self.priority)
        self.buttons = [self.save_btn]
        row = None
        for index, (label, action) in enumerate((("Atualizar / Refresh", "list"), ("Adicionar / Add", "add"),
                              ("Alterar / Update", "update"), ("Concluir / Complete", "complete"),
                              ("Reabrir / Reopen", "reopen"), ("Arquivar / Archive", "archive"),
                              ("Sincronizar / Sync", "sync"))):
            if index % 3 == 0:
                row = QHBoxLayout()
                layout.addLayout(row)
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, a=action: self._execute(a))
            self.buttons.append(button)
            row.addWidget(button)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.finished_work.connect(self._finish)
        self.kind.currentIndexChanged.connect(lambda: self._execute("list"))
        self.filter.currentIndexChanged.connect(lambda: self._execute("list"))
        self._execute("list")

    def _select(self):
        index = self.display.currentRow()
        if 0 <= index < len(self.rows):
            item = self.rows[index]
            self.selected_id = item["id"]
            self.title.setText(item["title"])
            self.due.setText(item.get("due") or "")
            self.priority.setCurrentIndex(max(0, self.priority.findData(item.get("priority", "normal"))))

    def _save(self):
        try:
            save_plugin_config("agenda", {"enabled": self.enabled.isChecked(),
                                         "list_id": self.list_id.text().strip()})
            self.status.setText("Configuração salva / Settings saved")
        except Exception:
            self.status.setText("Falha ao salvar / Save failed")

    def _execute(self, action):
        values = {"action": action, "title": self.title.text(), "due": self.due.text(),
                  "kind": self.kind.currentData(), "filter": self.filter.currentData()}
        if action not in ("list", "add", "sync") and self.selected_id:
            values.update(id=self.selected_id, new_title=self.title.text())
        if values["kind"] == "task":
            values["priority"] = self.priority.currentData()
        # Listing is local and does not hold UI widgets on a worker thread.
        for button in self.buttons + [self.kind, self.filter]:
            button.setEnabled(False)
        self.status.setText("Processando / Working…")
        def work():
            try:
                from plugins.organizer import run, _filtered
                from core import agenda_store, organizer_store, agenda_sync
                result = agenda_sync.sync_now() if action == "sync" else run(values)
                records = (agenda_store.all_events(True) if values["kind"] == "event" else organizer_store.tasks())
                events = json.dumps(_filtered(records, values["filter"]), ensure_ascii=False)
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
        self.rows = json.loads(events) if events else []
        self.display.blockSignals(True)
        self.display.setRowCount(len(self.rows))
        for row, item in enumerate(self.rows):
            state = ("Arquivado / Archived" if item.get("archived") else
                     "Concluído / Done" if item.get("done") else "Aberto / Open")
            if item.get("sync_issue"):
                state += " — " + str(item["sync_issue"])
            for col, value in enumerate((item["title"], item.get("due") or "—", state,
                                        {"low": "Baixa / Low", "high": "Alta / High"}.get(item.get("priority"), "Normal"))):
                self.display.setItem(row, col, QTableWidgetItem(value))
        self.display.clearSelection()
        self.selected_id = None
        self.display.blockSignals(False)
        self.display.resizeColumnsToContents()
        for button in self.buttons + [self.kind, self.filter]:
            button.setEnabled(True)
