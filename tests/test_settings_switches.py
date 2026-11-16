import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton
from gui.settings_controls import ToggleSwitch, ToggleRow
from gui.overlays import PluginSettingsOverlay
from gui.settings_panel import SettingsDialog
from memory import config_manager as config


class SettingsSwitchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for name, value in (('CONFIG_DIR', root), ('CONFIG_FILE', root / 'api_keys.json')):
            p = patch.object(config, name, value)
            p.start()
            self.addCleanup(p.stop)

    def test_switch_mouse_keyboard_and_disabled_state(self):
        switch = ToggleSwitch()
        switch.setAccessibleName('Ativar opção')
        switch.show()
        self.addCleanup(switch.close)
        QTest.mouseClick(switch, Qt.MouseButton.LeftButton)
        self.assertTrue(switch.isChecked())
        QTest.keyClick(switch, Qt.Key.Key_Space)
        self.assertFalse(switch.isChecked())
        switch.setEnabled(False)
        QTest.mouseClick(switch, Qt.MouseButton.LeftButton)
        self.assertFalse(switch.isChecked())

    def test_integration_switch_is_a_draft_until_save(self):
        panel = PluginSettingsOverlay([{'namespace': 'demo', 'fields': [
            {'key': 'enabled', 'label': 'Ativar serviço / Enable service', 'type': 'toggle'}],
            'values': {'enabled': False}}], compact=True)
        self.addCleanup(panel.close)
        switch = panel._widgets[('demo', 'enabled')]
        self.assertIsInstance(switch, ToggleSwitch)
        switch.click()
        self.assertEqual(config.get_plugin_config('demo'), {})
        panel._save_all()
        self.assertTrue(config.get_plugin_config('demo')['enabled'])
        row = panel.findChild(ToggleRow)
        self.assertEqual(row.state.text(), 'Ligado')
        self.assertEqual(row.label.text(), 'Ativar serviço')

    def test_runtime_refresh_does_not_trigger_actions_and_failure_reverts(self):
        host = QWidget()
        body = QVBoxLayout(host)
        source = QPushButton('Estado atual')
        active = [False]
        callback = Mock()
        row = SettingsDialog._runtime_toggle(None, body, 'Microfone', 'Teste', source, callback, lambda: active[0])
        self.assertFalse(row.switch.isChecked())
        row.switch.click()
        callback.assert_called_once()
        self.assertFalse(row.switch.isChecked())
        active[0] = True
        row.findChild(QTimer).timeout.emit()
        self.assertTrue(row.switch.isChecked())
        callback.assert_called_once()
        source.setEnabled(False)
        row.findChild(QTimer).timeout.emit()
        self.assertFalse(row.switch.isEnabled())
        host.close()

    def test_runtime_click_calls_existing_callback_once(self):
        host = QWidget()
        body = QVBoxLayout(host)
        active = [False]
        def apply():
            active[0] = not active[0]
        callback = Mock(side_effect=apply)
        row = SettingsDialog._runtime_toggle(None, body, 'Ativar', '', QPushButton(), callback, lambda: active[0])
        row.switch.click()
        callback.assert_called_once()
        self.assertTrue(row.switch.isChecked())
        self.assertEqual(row.state.text(), 'Ligado')
        host.close()

    def test_plugin_activation_preserves_persistence(self):
        from gui.overlays import PluginManagerOverlay
        config.save_plugin_enabled('demo', False)
        panel = PluginManagerOverlay([{'name': 'demo', 'valid': True, 'enabled': False,
                                       'description': 'Teste', 'file': 'demo.py'}])
        self.addCleanup(panel.close)
        switch = panel.findChild(ToggleSwitch)
        switch.click()
        self.assertTrue(config.get_plugin_enabled('demo'))
        self.assertTrue(switch.isChecked())
