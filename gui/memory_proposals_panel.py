"""Qt-only review of local factual proposals, separate from behaviour rules."""
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget
from core import memory_extraction as proposals


class MemoryProposalsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        label = QLabel("Sugestões locais de fatos. Só Aprovar salva; Rejeitar descarta. Não são regras de comportamento.")
        label.setWordWrap(True)
        layout.addWidget(label)
        self.rows = QListWidget()
        self.rows.setAccessibleName("Propostas de memória")
        layout.addWidget(self.rows)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        for title, action in (("Aprovar e salvar", self.accept), ("Rejeitar", self.reject)):
            button = QPushButton(title)
            button.clicked.connect(action)
            layout.addWidget(button)
        layout.addWidget(self.status)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1500)
        self.signature = None
        self.refresh()

    def refresh(self):
        rows = proposals.pending()
        signature = repr(rows)
        if signature == self.signature:
            return
        self.signature = signature
        self.rows.clear()
        for row in rows:
            old = row['previous']
            old = old.get('value', '') if isinstance(old, dict) else old
            item = QListWidgetItem(f"{row['category']}/{row['key']}: {row['value']}" +
                                   (f" (substitui: {old})" if old else ""))
            item.setData(Qt.ItemDataRole.UserRole, row['id'])
            self.rows.addItem(item)

    def accept(self):
        item = self.rows.currentItem()
        if item is None:
            return
        try:
            self.status.setText(proposals.accept_from_ui(item.data(Qt.ItemDataRole.UserRole)))
        except (ValueError, OSError) as exc:
            self.status.setText(str(exc))
        self.refresh()

    def reject(self):
        item = self.rows.currentItem()
        if item is not None:
            proposals.reject(item.data(Qt.ItemDataRole.UserRole))
            self.status.setText("Proposta rejeitada; nada salvo.")
            self.refresh()
