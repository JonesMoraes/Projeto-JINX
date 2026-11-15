"""Settings integration: real Qt widgets, isolated config and mocked hardware."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton, QWidget, QComboBox
from gui.settings_panel import SettingsDialog, CATEGORIES
from gui.settings_themes import SETTINGS_THEMES, settings_theme_id
from gui.theme import current_palette
from memory import config_manager as config


class SettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        directory = Path(self.temp.name)
        for name, value in (('CONFIG_DIR', directory), ('CONFIG_FILE', directory / 'api_keys.json')):
            item = patch.object(config, name, value)
            item.start()
            self.addCleanup(item.stop)
        self.host = QWidget()
        self.host.hud = Mock(hud_style='face')
        self.host.hud.available_styles.return_value = ('face', 'core')
        self.host.on_voice_preview_state = Mock()
        self.host.on_voice_change = Mock()
        self.host.get_plugin_settings = Mock(return_value=[{
            'namespace': 'demo', 'title': 'Conexão de teste',
            'fields': [{'key': 'enabled', 'type': 'toggle', 'label': 'Ativar'},
                       {'key': 'api_key', 'type': 'password', 'label': 'Credencial'}],
            'values': {'enabled': True, 'api_key': 'fixture-secret'},
        }])
        self.host.get_plugins = Mock(return_value=[])
        for name in ('_autostart_btn', '_brief_btn', '_wake_btn', '_ptt_btn', '_gesture_btn'):
            setattr(self.host, name, QPushButton(name, self.host))
        for name in ('_apply_name_update', '_refresh_identity_rows', '_set_hud_style',
                     '_on_audio_devices_applied', '_on_providers_applied', '_toggle_brief',
                     '_toggle_wake_word', '_toggle_ptt', '_toggle_gestures', '_open_remote',
                     '_create_desktop_shortcut', '_toggle_autostart', '_open_customize', '_preview_ui_color'):
            setattr(self.host, name, Mock())
        self.dialog = SettingsDialog(self.host)
        self.dialog.show()
        self.app.processEvents()

    def tearDown(self):
        self.dialog.close()
        self.host.close()
        self.host.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def test_hud_typography_and_no_emoji_in_settings_labels(self):
        from gui.style import DISPLAY_FAMILIES
        from gui.settings_panel import clean_settings_label
        from PyQt6.QtWidgets import QLineEdit
        self.assertEqual(clean_settings_label('🎙  PALAVRA DE ATIVAÇÃO'), 'PALAVRA DE ATIVAÇÃO')
        self.assertEqual(clean_settings_label('🔌  MOTOR DE IA'), 'MOTOR DE IA')
        self.assertEqual(clean_settings_label('⛶  TELA CHEIA [F11]'), 'TELA CHEIA [F11]')
        with patch('gui.providers_panel.threading.Thread'), patch('core.audio_devices.list_devices', return_value=[]):
            for key, *_ in CATEGORIES:
                self.dialog.show_category(key)
                self.app.processEvents()
                for widget in self.dialog.stack.currentWidget().findChildren(QWidget):
                    if isinstance(widget, (QLabel, QPushButton, QComboBox, QLineEdit)):
                        self.assertEqual(widget.font().families()[:len(DISPLAY_FAMILIES)], DISPLAY_FAMILIES,
                                         (key, type(widget).__name__))
                    if isinstance(widget, (QLabel, QPushButton)):
                        self.assertEqual(widget.text(), clean_settings_label(widget.text()), (key, widget.text()))
                    if isinstance(widget, QComboBox):
                        for idx in range(widget.count()):
                            self.assertEqual(widget.itemText(idx), clean_settings_label(widget.itemText(idx)), key)
        self.dialog.show_category('general')
        self.dialog.user_name.setText('💙 meu apelido')
        self.dialog._apply_theme()
        self.assertEqual(self.dialog.user_name.text(), '💙 meu apelido')

    def test_default_and_corrupt_preference_fall_back(self):
        self.assertEqual(self.dialog.theme_id, 'cyber_hud')
        for value in (None, {}, [], 'missing'):
            self.assertEqual(settings_theme_id(value), 'cyber_hud')

    def test_every_theme_click_persists_without_modifying_hud_or_credentials(self):
        config.update_config(gemini_api_key='fixture', ui_color='#123456', providers={'mode': 'pipeline'})
        original = current_palette()
        self.dialog.show_category('appearance')
        for key in SETTINGS_THEMES:
            self.dialog._theme_buttons[key].click()
            self.app.processEvents()
            self.assertEqual(config.load_api_keys()['settings_theme'], key)
            self.assertEqual(sum(b.isChecked() for b in self.dialog._theme_buttons.values()), 1)
            self.assertEqual(current_palette(), original)
        cfg = config.load_api_keys()
        self.assertEqual(cfg['gemini_api_key'], 'fixture')
        self.assertEqual(cfg['ui_color'], '#123456')
        self.assertEqual(cfg['providers'], {'mode': 'pipeline'})
        reopened = SettingsDialog(self.host)
        self.assertEqual(reopened.theme_id, 'neon_glass')
        reopened.deleteLater()
        self.dialog.select_theme('cyber_hud')
        self.assertEqual(config.load_api_keys()['settings_theme'], 'cyber_hud')

    def test_failed_save_keeps_previous_theme_and_selection(self):
        self.dialog.show_category('appearance')
        with patch.object(config, 'update_config', side_effect=OSError('disk full')):
            self.dialog._theme_buttons['minimal_light'].click()
        self.assertEqual(self.dialog.theme_id, 'cyber_hud')
        self.assertTrue(self.dialog._theme_buttons['cyber_hud'].isChecked())
        self.assertFalse(self.dialog._theme_buttons['minimal_light'].isChecked())
        self.assertIn('Não foi possível', self.dialog.status.text())

    def test_search_accents_plugin_names_empty_and_recovery(self):
        for query, category in (('aparencia', 'appearance'), ('microfone', 'audio'),
                                ('conexao de teste', 'integrations')):
            self.dialog.search.setText(query)
            self.assertEqual(self.dialog._current, category)
        self.dialog.search.setText('zzzzunknown')
        self.assertIs(self.dialog.stack.currentWidget(), self.dialog.empty)
        self.dialog.search.clear()
        self.assertIsNot(self.dialog.stack.currentWidget(), self.dialog.empty)
        self.assertFalse(any(self.dialog.navigation.item(i).isHidden() for i in range(len(CATEGORIES))))

    def test_drafts_survive_navigation_and_identity_save_uses_runtime_callback(self):
        self.dialog.assistant_name.setText('JINX Nova')
        self.dialog.user_name.setText('Thomas')
        self.dialog.show_category('appearance')
        self.dialog.show_category('general')
        self.assertEqual(self.dialog.assistant_name.text(), 'JINX Nova')
        self.button('Aplicar identidade').click()
        self.assertEqual(config.load_api_keys()['assistant_name'], 'JINX Nova')
        self.host._apply_name_update.assert_called_once_with('JINX Nova', 'Thomas')

    def button(self, text):
        return next(b for b in self.dialog.findChildren(QPushButton) if b.text() == text)

    def test_voice_preview_does_not_save_and_stops_on_navigation(self):
        self.dialog.show_category('audio')
        original = config.get_voice()
        self.dialog.voice.setCurrentIndex(0)
        with patch.object(self.dialog.preview.player, 'request') as request, \
                patch.object(self.dialog.preview.player, 'stop') as stop:
            self.button('Ouvir prévia').click()
            request.assert_called_once_with(self.dialog.voice.currentData())
            self.assertEqual(config.get_voice(), original)
            self.dialog.show_category('general')
            stop.assert_called_once()
        self.dialog.show_category('audio')
        self.button('Aplicar voz').click()
        self.assertEqual(config.get_voice(), self.dialog.voice.currentData())

    def test_audio_save_stays_visible_and_only_changed_device_reconnects(self):
        from gui.overlays import AudioDeviceOverlay
        with patch('core.audio_devices.list_devices', return_value=[]):
            self.dialog.show_category('audio')
        audio = self.dialog.findChild(AudioDeviceOverlay)
        audio._apply()
        self.assertFalse(audio.isHidden())
        self.host._on_audio_devices_applied.assert_not_called()
        audio._in_box.addItem('Test microphone', 'fixture-mic')
        audio._in_box.setCurrentIndex(audio._in_box.count() - 1)
        audio._apply()
        self.host._on_audio_devices_applied.assert_called_once()
        self.assertFalse(audio.isHidden())

    def test_plugin_credentials_collapsed_masked_and_saved_in_own_namespace(self):
        from gui.overlays import PluginSettingsOverlay
        self.dialog.show_category('integrations')
        panel = self.dialog.findChild(PluginSettingsOverlay)
        secret = panel._widgets[('demo', 'api_key')]
        self.assertFalse(secret.isVisible())
        self.assertEqual(secret.echoMode(), secret.EchoMode.Password)
        self.button('Credenciais e opções avançadas').click()
        self.assertTrue(secret.isVisible())
        secret.setText('updated-fixture')
        panel._save_all()
        self.assertEqual(config.get_plugin_config('demo')['api_key'], 'updated-fixture')

    def test_all_categories_render_and_providers_fit_available_width(self):
        with patch('gui.providers_panel.threading.Thread'), patch('core.audio_devices.list_devices', return_value=[]):
            for key, *_ in CATEGORIES:
                self.dialog.show_category(key)
                self.app.processEvents()
                labels = self.dialog.stack.currentWidget().findChildren(QLabel)
                self.assertFalse(any('Não foi possível abrir' in label.text() for label in labels), key)
                self.assertEqual(self.dialog.stack.currentWidget().horizontalScrollBar().maximum(), 0, key)
            self.dialog.show_category('ai')
            for theme in SETTINGS_THEMES:
                self.dialog.select_theme(theme)
                self.app.processEvents()
                self.assertEqual(self.dialog.stack.currentWidget().horizontalScrollBar().maximum(), 0)
            self.dialog.resize(760, 540)
            for key, *_ in CATEGORIES:
                self.dialog.show_category(key)
                self.app.processEvents()
                self.assertEqual(self.dialog.stack.currentWidget().horizontalScrollBar().maximum(), 0, key)

    def test_provider_apply_reconnects_once_and_dynamic_controls_follow_theme(self):
        from gui.providers_panel import ProvidersOverlay
        with patch('gui.providers_panel.threading.Thread'):
            self.dialog.show_category('ai')
            panel = self.dialog.findChild(ProvidersOverlay)
            panel._set_mode('pipeline')
            self.app.processEvents()
            panel._apply()
            self.host._on_providers_applied.assert_called_once()
            self.assertFalse(panel.isHidden())
            panel._apply()
            self.host._on_providers_applied.assert_called_once()
            self.dialog.select_theme('minimal_light')
            self.dialog.resize(760, 540)
            self.app.processEvents()
            self.assertEqual(self.dialog.stack.currentWidget().horizontalScrollBar().maximum(), 0)

    def test_cyber_hud_follows_actual_accent_other_themes_stay_independent(self):
        from gui.theme import C, apply_ui_accent, retheme_all_widgets, current_palette
        from gui.settings_themes import resolved_settings_theme
        self.dialog.show_category('integrations')
        panel = self.dialog._embedded[-1]
        original = [w.styleSheet() for w in panel.findChildren(QWidget)]
        palette = current_palette()
        try:
            apply_ui_accent('#993399')
            retheme_all_widgets(palette, current_palette())
            self.dialog.select_theme('minimal_light')
            self.assertEqual(resolved_settings_theme('minimal_light').accent, SETTINGS_THEMES['minimal_light'].accent)
            self.dialog.select_theme('cyber_hud')
            self.assertEqual(resolved_settings_theme('cyber_hud').accent, C.PRI)
            self.assertEqual(resolved_settings_theme('cyber_hud').bg, C.BG)
            self.assertNotEqual([w.styleSheet() for w in panel.findChildren(QWidget)], original)
            self.assertTrue(any(C.PRI.lower() in w.styleSheet().lower() for w in panel.findChildren(QWidget)))
        finally:
            for key, value in palette.items():
                setattr(C, key, value)
            self.dialog._apply_theme()

    def test_hud_color_validation_and_independent_persistence(self):
        self.dialog.show_category('appearance')
        self.dialog.hud_color.setText('invalid')
        self.dialog._save_hud_color()
        self.host._preview_ui_color.assert_not_called()
        self.dialog.hud_color.setText('#663399')
        self.dialog._save_hud_color()
        self.host._preview_ui_color.assert_called_once_with('#663399')
        self.assertEqual(config.load_api_keys()['ui_color'], '#663399')
        self.assertEqual(self.dialog.theme_id, 'cyber_hud')

    def test_embedded_form_rethemes_back_to_exact_original_palette(self):
        self.dialog.show_category('integrations')
        panel = self.dialog._embedded[-1]
        original = [w.styleSheet() for w in panel.findChildren(QWidget)]
        self.dialog.select_theme('minimal_light')
        self.dialog.select_theme('cyber_hud')
        self.assertEqual([w.styleSheet() for w in panel.findChildren(QWidget)], original)


if __name__ == '__main__':
    unittest.main()
