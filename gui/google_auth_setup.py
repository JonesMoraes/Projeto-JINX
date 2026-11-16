"""Qt-thread-only setup before the existing worker/browser OAuth flow."""
from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QDialog, QFileDialog, QLabel, QLineEdit, QPushButton, QVBoxLayout
from core import google_workspace as google
from gui.theme import C
from gui.style import hud_font

CLOUD_CLIENTS = "https://console.cloud.google.com/auth/clients"


class GoogleAuthSetup(QDialog):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = dict(cfg)
        self.setWindowTitle("Preparar login Google pelo navegador")
        self.setMinimumWidth(520)
        self.setFont(hud_font(10))
        self.setStyleSheet(f"background:{C.BG};color:{C.TEXT};")
        layout = QVBoxLayout(self)
        label = QLabel("A autenticação acontece no navegador. Na primeira conexão, o Google exige um cliente OAuth Desktop para identificar a JINX.\n\n1. No Google Cloud, habilite as APIs desejadas e configure o consentimento.\n2. Crie um cliente do tipo Aplicativo para computador.\n3. Importe o JSON ou preencha os dados abaixo. Depois autorize sua conta no navegador.")
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(label)
        cloud = QPushButton("Abrir Google Cloud no navegador")
        cloud.clicked.connect(self.open_cloud)
        layout.addWidget(cloud)
        importer = QPushButton("Importar JSON do Google e continuar")
        importer.clicked.connect(self.import_json)
        layout.addWidget(importer)
        layout.addWidget(QLabel("Ou informe os dados do cliente OAuth Desktop:"))
        self.client_id = QLineEdit()
        self.client_id.setPlaceholderText("ID do cliente — …apps.googleusercontent.com")
        self.client_id.setAccessibleName("ID do cliente OAuth Desktop")
        layout.addWidget(self.client_id)
        self.client_secret = QLineEdit()
        self.client_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.client_secret.setPlaceholderText("Segredo do cliente (não é a senha Google)")
        self.client_secret.setAccessibleName("Segredo do cliente OAuth Desktop")
        layout.addWidget(self.client_secret)
        save = QPushButton("Salvar cliente e continuar para o login")
        save.clicked.connect(self.save_client)
        layout.addWidget(save)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel)
        self.status = QLabel("")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

    def open_cloud(self):
        if not QDesktopServices.openUrl(QUrl(CLOUD_CLIENTS)):
            self.status.setText("Não foi possível abrir o navegador. Acesse console.cloud.google.com/auth/clients.")

    def import_json(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Escolher JSON OAuth Desktop", "", "JSON (*.json)")
        if not filename:
            return
        self.configure(source=filename)

    def save_client(self):
        self.configure(client_id=self.client_id.text(), client_secret=self.client_secret.text())

    def configure(self, **kwargs):
        try:
            google.configure_desktop_client(self.cfg, **kwargs)
        except google.GoogleError as exc:
            self.status.setText(str(exc))
            return
        except OSError:
            self.status.setText("Não foi possível salvar a configuração local. Confira as permissões da pasta config.")
            return
        self.client_secret.clear()
        self.accept()


def ensure_google_client(parent, cfg):
    try:
        google.client_definition(cfg)
        return True
    except google.GoogleError:
        dialog = GoogleAuthSetup(cfg, parent)
        return dialog.exec() == QDialog.DialogCode.Accepted
