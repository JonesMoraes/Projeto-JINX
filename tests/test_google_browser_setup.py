import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from core import google_workspace as api


class BrowserSetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        patcher = patch.object(api, 'CONFIG_DIR', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cfg = {'client_file': 'google_client_secret.json', 'calendar': True}

    def test_manual_client_prepares_browser_auth_without_json_download(self):
        api.configure_desktop_client(self.cfg, client_id='test.apps.googleusercontent.com', client_secret='desktop-secret')
        data = api.client_definition(self.cfg)
        self.assertEqual(data['installed']['token_uri'], 'https://oauth2.googleapis.com/token')
        self.assertFalse((self.root / api.TOKEN_NAME).exists())
        self.assertEqual(self.cfg, {'client_file': 'google_client_secret.json', 'calendar': True})

    def test_invalid_import_preserves_existing_client_and_token(self):
        api.configure_desktop_client(self.cfg, client_id='test.apps.googleusercontent.com', client_secret='desktop-secret')
        existing = (self.root / self.cfg['client_file']).read_bytes()
        token = self.root / api.TOKEN_NAME
        token.write_text('previous-token')
        source = self.root / 'bad.json'
        source.write_text(json.dumps({'web': {'client_id': 'bad'}}))
        with self.assertRaises(api.GoogleError):
            api.configure_desktop_client(self.cfg, source=source)
        self.assertEqual((self.root / self.cfg['client_file']).read_bytes(), existing)
        self.assertEqual(token.read_text(), 'previous-token')

    def test_custom_endpoints_and_missing_secret_rejected(self):
        for identity, secret in (('wrong', 'secret'), ('test.apps.googleusercontent.com', '')):
            with self.assertRaises(api.GoogleError):
                api.configure_desktop_client(self.cfg, client_id=identity, client_secret=secret)
        self.assertFalse((self.root / self.cfg['client_file']).exists())

    def test_dialog_manual_save_prepares_then_accepts(self):
        from gui.google_auth_setup import GoogleAuthSetup, ensure_google_client
        dialog = GoogleAuthSetup(self.cfg)
        dialog.client_id.setText('test.apps.googleusercontent.com')
        dialog.client_secret.setText('desktop-secret')
        dialog.save_client()
        self.assertEqual(dialog.result(), dialog.DialogCode.Accepted)
        self.assertEqual(dialog.client_secret.text(), '')
        self.assertTrue(ensure_google_client(None, self.cfg))
        dialog.close()

    def test_file_picker_cancel_has_no_effect(self):
        from gui.google_auth_setup import GoogleAuthSetup
        dialog = GoogleAuthSetup(self.cfg)
        with patch('gui.google_auth_setup.QFileDialog.getOpenFileName', return_value=('', '')):
            dialog.import_json()
        self.assertFalse((self.root / self.cfg['client_file']).exists())
        dialog.close()

    def test_browser_setup_link_is_fixed_and_failure_is_visible(self):
        from gui.google_auth_setup import GoogleAuthSetup, CLOUD_CLIENTS
        dialog = GoogleAuthSetup(self.cfg)
        with patch('gui.google_auth_setup.QDesktopServices.openUrl', return_value=False) as opened:
            dialog.open_cloud()
        self.assertEqual(opened.call_args.args[0].toString(), CLOUD_CLIENTS)
        self.assertIn('Não foi possível', dialog.status.text())
        dialog.close()

    def test_agenda_cancel_does_not_start_browser_login(self):
        from gui.agenda_panel import AgendaPanel
        with patch.object(AgendaPanel, '_execute'), patch.object(AgendaPanel, '_save', return_value=True), \
             patch('gui.agenda_panel.get_plugin_config', return_value=self.cfg), \
             patch('gui.google_auth_setup.ensure_google_client', return_value=False), \
             patch.object(api, 'connect') as connect:
            panel = AgendaPanel()
            panel._connect_google()
            connect.assert_not_called()
            self.assertTrue(panel.connect_btn.isEnabled())
            self.assertIn('cancelado', panel.status.text())
            panel.close()
