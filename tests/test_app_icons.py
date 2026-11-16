import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from core import app_icons
from memory import config_manager as config


class AppIconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name, value in (('CONFIG_DIR', self.root), ('CONFIG_FILE', self.root / 'api_keys.json')):
            p = patch.object(config, name, value)
            p.start()
            self.addCleanup(p.stop)

    def test_user_catalog_has_ten_loadable_icons(self):
        icons = app_icons.available_icons()
        self.assertEqual(len(icons), 10)
        for row in icons:
            self.assertFalse(QIcon(str(row['path'])).pixmap(64, 64).isNull(), row['id'])

    def test_selection_persists_and_preserves_other_settings(self):
        config.update_config(user_name='Fixture', providers={'mode': 'pipeline'})
        chosen = app_icons.CATALOG[6][0]
        app_icons.select(chosen)
        self.assertEqual(app_icons.selected_id(), chosen)
        self.assertEqual(app_icons.selected_path().stem, chosen)
        self.assertEqual(config.load_api_keys()['user_name'], 'Fixture')
        self.assertEqual(config.load_api_keys()['providers'], {'mode': 'pipeline'})

    def test_invalid_choice_does_not_change_config(self):
        app_icons.select(app_icons.DEFAULT_ICON)
        before = config.CONFIG_FILE.read_bytes()
        for invalid in ('../outside', 'C:/outside.ico', 'missing', None):
            with self.assertRaises(ValueError):
                app_icons.select(invalid)
        self.assertEqual(config.CONFIG_FILE.read_bytes(), before)

    def test_invalid_saved_preference_falls_back(self):
        for value in ([], {}, 'missing'):
            config.update_config(app_icon=value)
            self.assertEqual(app_icons.selected_id(), app_icons.DEFAULT_ICON)

    def test_shortcut_updates_icon_only_for_this_installation(self):
        (self.root / 'JINX.lnk').touch()
        (self.root / 'Other.lnk').touch()
        own = SimpleNamespace(TargetPath=str(app_icons.ROOT / '.jinx_runtime/pythonw.exe'),
                              Arguments='original arguments', WorkingDirectory='original directory',
                              IconLocation='old.ico', Save=Mock())
        other = SimpleNamespace(TargetPath=str(self.root / 'Other.exe'), IconLocation='other.ico', Save=Mock())
        shell = Mock()
        shell.CreateShortcut.side_effect = lambda path: own if Path(path).name == 'JINX.lnk' else other
        result = app_icons.update_shortcuts(self.root, shell=shell)
        self.assertEqual(result['updated'], ['JINX.lnk'])
        self.assertEqual(result['failed'], [])
        self.assertEqual(own.Arguments, 'original arguments')
        self.assertEqual(own.WorkingDirectory, 'original directory')
        self.assertTrue(own.IconLocation.endswith('.ico,0'))
        other.Save.assert_not_called()

    def test_gallery_draft_apply_and_window_icon(self):
        from gui.app_icon_picker import AppIconPicker
        host = QWidget()
        self.addCleanup(host.close)
        panel = AppIconPicker(host)
        self.addCleanup(panel.close)
        item = panel.gallery.item(3)
        panel.gallery.setCurrentItem(item)
        self.assertNotIn('app_icon', config.load_api_keys())
        with patch.object(app_icons, 'update_shortcuts', return_value={'updated': ['JINX.lnk'], 'failed': []}):
            panel.apply_button.click()
        self.assertEqual(app_icons.selected_id(), item.data(Qt.ItemDataRole.UserRole))
        self.assertFalse(host.windowIcon().isNull())
        self.assertIn('Atalhos atualizados: 1', panel.status.text())

    def test_shortcut_failure_does_not_claim_full_success(self):
        from gui.app_icon_picker import AppIconPicker
        host = QWidget()
        self.addCleanup(host.close)
        panel = AppIconPicker(host)
        self.addCleanup(panel.close)
        with patch.object(app_icons, 'update_shortcuts', return_value={'updated': [], 'failed': ['JINX.lnk']}):
            panel.apply()
        self.assertIn('Não foi possível atualizar', panel.status.text())
