"""Agenda dialog. All network/store work runs on workers; UI stays on Qt."""
import json
import threading
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QCheckBox, QComboBox, QTableWidget, QTableWidgetItem, QAbstractItemView)
from gui.theme import C
from gui.settings_controls import ToggleRow
from gui.style import hud_font
from memory.config_manager import get_plugin_config, save_plugin_config


class AgendaPanel(QDialog):
    finished_work = pyqtSignal(str, str)
    connection_finished = pyqtSignal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Agenda — Google Agenda")
        self.resize(720, 680)
        self.setFont(hud_font(10))
        self.setStyleSheet(f"background:{C.BG};color:{C.TEXT};")
        layout = QVBoxLayout(self)
        instructions = QLabel('Tarefas e eventos locais continuam disponíveis sem conta.\n'
            'Google Agenda: salve as configurações, conecte sua conta e use Sincronizar.\n'
            'Use Entrar com Google; na primeira vez, a preparação abre na própria tela.\n'
            'Não há sincronização automática; arquivar/desfazer localmente não apaga eventos no Google.')
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        cfg = get_plugin_config("google_workspace")
        sync_row = ToggleRow("Sincronização manual com Google Agenda")
        self.enabled = sync_row.switch
        self.enabled.setChecked(cfg.get("calendar_sync") is True)
        layout.addWidget(sync_row)
        self.calendar_id = QLineEdit(str(cfg.get('calendar_id') or 'primary'))
        self.calendar_id.setPlaceholderText('ID do Google Agenda (primary = calendário principal)')
        self.calendar_id.setToolTip('primary usa seu calendário principal; outros calendários exigem o ID e acesso da conta conectada.')
        layout.addWidget(self.calendar_id)
        self.client_file = QLineEdit(str(cfg.get('client_file') or 'google_client_secret.json'))
        self.client_file.setPlaceholderText('Arquivo JSON OAuth Desktop dentro de config/')
        self.client_file.setToolTip('Nome/caminho relativo do JSON OAuth Desktop, armazenado dentro de config/.')
        layout.addWidget(self.client_file)
        self.save_btn = QPushButton("Salvar configuração")
        self.save_btn.clicked.connect(self._save)
        layout.addWidget(self.save_btn)
        self.connect_btn = QPushButton('Entrar com Google no navegador')
        self.connect_btn.clicked.connect(self._connect_google)
        layout.addWidget(self.connect_btn)
        self.kind = QComboBox()
        self.kind.addItem("Tarefas", "task")
        self.kind.addItem("Eventos", "event")
        self.kind.setCurrentIndex(1)
        layout.addWidget(self.kind)
        self.filter = QComboBox()
        for label, value in (("Abertos", "open"), ("Hoje", "today"),
                             ("Amanhã", "tomorrow"), ("Atrasados", "overdue"),
                             ("Concluídos", "done"), ("Todos", "all")):
            self.filter.addItem(label, value)
        layout.addWidget(self.filter)
        self.display = QTableWidget(0, 4)
        self.display.setHorizontalHeaderLabels(["Título", "Data", "Estado", "Prioridade"])
        self.display.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.display.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.display.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.display.itemSelectionChanged.connect(self._select)
        self.rows = []
        self.selected_id = None
        layout.addWidget(self.display)
        self.title = QLineEdit()
        self.title.setPlaceholderText("Título exato do evento")
        layout.addWidget(self.title)
        self.due = QLineEdit()
        self.due.setPlaceholderText("2026-11-14T17:00:00-03:00")
        layout.addWidget(self.due)
        self.priority = QComboBox()
        for label, value in (("Baixa", "low"), ("Normal", "normal"), ("Alta", "high")):
            self.priority.addItem(label, value)
        self.priority.setCurrentIndex(1)
        layout.addWidget(self.priority)
        self.buttons = [self.save_btn, self.connect_btn]
        row = None
        for index, (label, action) in enumerate((("Atualizar", "list"), ("Adicionar", "add"),
                              ("Alterar", "update"), ("Concluir", "complete"),
                              ("Reabrir", "reopen"), ("Arquivar", "archive"),
                              ("Sincronizar Google Agenda", "sync"))):
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
        self.connection_finished.connect(self._finish_connection)
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
            save_plugin_config('agenda', {'provider': 'google', 'enabled': False})
            save_plugin_config('google_workspace', {'calendar': True,
                'calendar_sync': self.enabled.isChecked(),
                'calendar_id': self.calendar_id.text().strip() or 'primary',
                'client_file': self.client_file.text().strip() or 'google_client_secret.json'})
            self.status.setText('Google Agenda selecionado. Conecte sua conta se necessário; nenhum evento foi enviado.')
            return True
        except Exception:
            self.status.setText("Falha ao salvar")
            return False

    def _connect_google(self):
        if not self._save():
            return
        values = get_plugin_config('google_workspace')
        from gui.google_auth_setup import ensure_google_client
        if not ensure_google_client(self, values):
            self.status.setText('Login cancelado. Sua conta anterior e os eventos foram preservados.')
            return
        for button in self.buttons + [self.kind, self.filter]:
            button.setEnabled(False)
        self.status.setText('Autorize no navegador. Se YouTube estiver selecionado, haverá uma segunda etapa separada de Gmail, Agenda e Drive. Nenhum evento será enviado ao conectar.')
        def connect():
            try:
                from core.google_workspace import connect as oauth_connect
                ok, message = oauth_connect(values)
            except Exception:
                ok, message = False, 'Conexão Google não concluída. Confira o arquivo OAuth e a conexão.'
            try:
                self.connection_finished.emit(ok, message)
            except RuntimeError:
                pass
        threading.Thread(target=connect, daemon=True, name='agenda-google-login').start()

    def _finish_connection(self, ok, message):
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setText(message + (' Use Sincronizar Google Agenda para enviar/receber eventos.' if ok else ''))
        for button in self.buttons + [self.kind, self.filter]:
            button.setEnabled(True)

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
        self.status.setText("Processando…")
        def work():
            try:
                from plugins.organizer import run, _filtered
                from core import agenda_store, organizer_store, agenda_sync
                result = agenda_sync.display_result(agenda_sync.sync_now()) if action == "sync" else run(values)
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
            state = ("Arquivado" if item.get("archived") else
                     "Concluído" if item.get("done") else "Aberto")
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
