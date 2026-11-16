"""Settings page for reviewed behaviour rules (⚙ → Regras aprendidas / Learned Rules).

Qt thread only. Every change goes through core.learned_rules, after the user
has seen the change and confirmed it in a dialog.
"""
from PyQt6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel,
                             QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
                             QPushButton, QVBoxLayout, QWidget)

from core import learned_rules as rules


class LearnedRulesPanel(QWidget):
    """Create, review, edit, enable, disable, remove, export and import rules."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LearnedRulesPanel")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        self.status = QLabel("")
        self.status.setWordWrap(True)

        # Create: a typed rule becomes a proposal, which is stored only after a second confirmation.
        root.addWidget(QLabel("Nova regra (texto em uma frase imperativa)"))
        create_row = QHBoxLayout()
        self.new_text = QLineEdit()
        self.new_text.setPlaceholderText("Ex.: Always respond in Portuguese.")
        self.new_text.setAccessibleName("Texto da nova regra")
        self.new_kind = QComboBox()
        for kind in rules.KINDS:
            self.new_kind.addItem(kind, kind)
        create_row.addWidget(self.new_text, 1)
        create_row.addWidget(self.new_kind)
        propose = QPushButton("Propor regra")
        propose.clicked.connect(self._propose)
        create_row.addWidget(propose)
        root.addLayout(create_row)

        # Review pending proposals.
        root.addWidget(QLabel("Propostas aguardando aprovação"))
        self.pending_list = QListWidget()
        self.pending_list.setAccessibleName("Propostas pendentes")
        root.addWidget(self.pending_list)
        pending_row = QHBoxLayout()
        accept = QPushButton("Aprovar e salvar")
        accept.clicked.connect(self._accept_pending)
        discard = QPushButton("Descartar")
        discard.clicked.connect(self._discard_pending)
        pending_row.addWidget(accept)
        pending_row.addWidget(discard)
        root.addLayout(pending_row)

        # Stored rules.
        root.addWidget(QLabel("Regras salvas"))
        self.rule_list = QListWidget()
        self.rule_list.setAccessibleName("Regras salvas")
        root.addWidget(self.rule_list)
        actions = QHBoxLayout()
        for label, slot in (("Editar", self._edit),
                            ("Ativar / desativar", self._toggle),
                            ("Remover", self._remove)):
            button = QPushButton(label)
            button.clicked.connect(slot)
            actions.addWidget(button)
        root.addLayout(actions)

        backup = QHBoxLayout()
        export = QPushButton("Exportar backup (JSON)")
        export.clicked.connect(self._export)
        importer = QPushButton("Importar backup (JSON)")
        importer.clicked.connect(self._import)
        backup.addWidget(export)
        backup.addWidget(importer)
        root.addLayout(backup)
        root.addWidget(self.status)

        self.refresh()

    # ── Display ──────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        self.pending_list.clear()
        for row in rules.pending():
            item = QListWidgetItem(f"{row['text']}\n[{row['kind']}] proposta")
            item.setData(256, row["id"])  # Qt.ItemDataRole.UserRole
            self.pending_list.addItem(item)
        self.rule_list.clear()
        try:
            stored = rules.list_rules()
        except (ValueError, OSError) as exc:
            self._say(f"Arquivo de regras com problema: {exc}")
            return
        for row in stored:
            state = "ATIVA" if row["enabled"] else "DESATIVADA"
            item = QListWidgetItem(
                f"[{state}] prioridade {row['priority']} · {row['text']}\n"
                f"id {row['id']} · criada em {row['created_at'][:10]} · origem: {row['source']} · "
                f"escopo: {row['scope']} · tipo: {row['kind']}")
            item.setData(256, row["id"])
            self.rule_list.addItem(item)

    def _say(self, text: str) -> None:
        self.status.setText(text)

    def _selected_id(self, widget: QListWidget) -> str | None:
        item = widget.currentItem()
        if item is None:
            self._say("Selecione uma regra primeiro.")
            return None
        return item.data(256)

    def _confirm(self, title: str, text: str) -> bool:
        answer = QMessageBox.question(self, title, text,
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes

    def _report(self, result: str, done_text: str) -> None:
        if rules.status_ok(result):
            self._say(done_text)
        else:
            self._say(_reason(result))
        self.refresh()

    # ── Create and review ────────────────────────────────────────────────────

    def _propose(self) -> None:
        try:
            row = rules.propose(self.new_text.text(), self.new_kind.currentData(), source="panel")
        except ValueError as exc:
            self._say(str(exc))
            return
        self.new_text.clear()
        self._say("Proposta criada. Aprove para salvar; nada foi salvo ainda.")
        self.refresh()
        return row

    def _accept_pending(self) -> None:
        proposal_id = self._selected_id(self.pending_list)
        if proposal_id is None:
            return
        text = next((r["text"] for r in rules.pending() if r["id"] == proposal_id), "")
        if not self._confirm("Salvar regra", f"Salvar esta regra?\n\n{text}"):
            self._say("Nada foi salvo.")
            return
        self._report(rules.accept_pending(proposal_id), "Regra salva.")

    def _discard_pending(self) -> None:
        proposal_id = self._selected_id(self.pending_list)
        if proposal_id is not None:
            self._report(rules.reject(proposal_id), "Proposta descartada.")

    # ── Change stored rules ──────────────────────────────────────────────────

    def _apply(self, action: str, rule_id: str, **fields) -> None:
        try:
            change = rules.prepare(action, rule_id, **fields)
        except (LookupError, ValueError) as exc:
            self._say(str(exc))
            return
        if not self._confirm("Confirmar alteração", change["summary"]):
            self._say("Nenhuma alteração feita.")
            return
        self._report(rules.apply_change(change), "Alteração salva.")

    def _edit(self) -> None:
        rule_id = self._selected_id(self.rule_list)
        if rule_id is None:
            return
        current = next((r for r in rules.list_rules() if r["id"] == rule_id), None)
        if current is None:
            self.refresh()
            return
        text, ok = QInputDialog.getText(self, "Editar regra", "Texto da regra:", text=current["text"])
        if not ok:
            return
        priority, ok = QInputDialog.getInt(self, "Editar regra", "Prioridade (0 a 1000):",
                                           value=current["priority"],
                                           min=rules.PRIORITY_MIN, max=rules.PRIORITY_MAX)
        if not ok:
            return
        self._apply("edit", rule_id, text=text, priority=priority)

    def _toggle(self) -> None:
        rule_id = self._selected_id(self.rule_list)
        if rule_id is None:
            return
        current = next((r for r in rules.list_rules() if r["id"] == rule_id), None)
        if current is None:
            self.refresh()
            return
        self._apply("disable" if current["enabled"] else "enable", rule_id)

    def _remove(self) -> None:
        rule_id = self._selected_id(self.rule_list)
        if rule_id is not None:
            self._apply("remove", rule_id)

    # ── Backup ───────────────────────────────────────────────────────────────

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Exportar regras", "jinx-regras.json",
                                              "JSON (*.json)")
        if path:
            self._report(rules.export_rules(path), "Backup exportado.")

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importar regras", "", "JSON (*.json)")
        if not path:
            return
        try:
            incoming = rules.read_import(path)
        except ValueError as exc:
            self._say(str(exc))
            return
        preview = "\n".join(f"- {r['text']}" for r in incoming[:20]) or "(nenhuma regra)"
        if not self._confirm("Importar regras",
                             f"{len(incoming)} regra(s) no arquivo. As já existentes não serão alteradas.\n\n"
                             f"{preview}\n\nImportar as novas?"):
            self._say("Importação cancelada.")
            return
        self._report(rules.merge_import(incoming), "Importação concluída.")


def _reason(result: str) -> str:
    """The reason part of a status line, for a person to read."""
    marker = 'reason="'
    if marker in result:
        return result.split(marker, 1)[1].split('"', 1)[0]
    return "Não foi possível concluir. Veja o log da JINX."
