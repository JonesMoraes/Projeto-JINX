import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtGui import QImage, QColor
from PyQt6.QtWidgets import QApplication, QPushButton
from gui.window import MainWindow
from ui import JinxUI
from plugins import display_control


class ImmersiveDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        for name, value in (
            ('gui.window._read_full_config', {'assistant_name': 'JINX', 'gemini_api_key': 'fake', 'os_system': 'Windows'}),
            ('gui.window.HAVE_VIDEO', False),
            ('memory.config_manager.get_hud_style', 'face'),
        ):
            p = patch(name, return_value=value) if name != 'gui.window.HAVE_VIDEO' else patch(name, value)
            p.start(); self.addCleanup(p.stop)
        self.window = MainWindow('face.png')
        self.window.show()
        self.app.processEvents()
        self.mode = self.window._orb_mode

    def tearDown(self):
        self.mode.close_popup()
        self.window._set_meeting_recording(False)
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def fullscreen(self):
        self.window.showFullScreen()
        self.app.processEvents()
        self.assertTrue(self.mode.active)

    def test_fullscreen_only_orb_and_restore_panels_and_style(self):
        self.window._show_content('Anterior', 'Texto anterior')
        self.fullscreen()
        self.assertTrue(self.window.hud.immersive)
        self.assertEqual(self.window.hud.hud_style, 'core')
        for widget in (self.window._header, self.window._left_panel, self.window._right_panel,
                       self.window._status_strip, self.window._content_panel, self.window._quiz_panel):
            self.assertTrue(widget.isHidden())
        self.assertEqual(self.window._hud_cam_stack.currentIndex(), 0)
        self.window._toggle_fullscreen()
        self.app.processEvents()
        self.assertFalse(self.mode.active)
        self.assertFalse(self.window.hud.immersive)
        self.assertEqual(self.window.hud.hud_style, 'face')
        self.assertTrue(self.window._header.isVisible())
        self.assertTrue(self.window._content_panel.isVisible())

    def test_application_startup_is_always_fullscreen_without_changing_settings(self):
        with patch('core.audio_devices.prefetch') as prefetch:
            player = JinxUI('face.png')
        try:
            self.app.processEvents()
            self.assertTrue(player._win.isFullScreen())
            self.assertTrue(player._win._orb_mode.active)
            self.assertTrue(player._win.hud.immersive)
            prefetch.assert_called_once()
        finally:
            player._win.close()
            player._win.deleteLater()

    def test_audio_test_panel_prevents_overlapping_tests(self):
        from gui.overlays import AudioDeviceOverlay
        from PyQt6.QtWidgets import QLabel
        with patch('core.audio_devices.list_devices', return_value=['Device']), \
                patch('core.audio_devices.get_output_volume', return_value=40):
            overlay = AudioDeviceOverlay(self.window.centralWidget())
        try:
            buttons = overlay._test_buttons
            with patch('threading.Thread') as thread:
                overlay._run_test('input', overlay._in_box, buttons[0], QLabel())
                self.assertTrue(all(not button.isEnabled() for button in buttons))
                overlay._run_test('output', overlay._out_box, buttons[1], QLabel())
                self.assertEqual(thread.call_count, 1)
            overlay._on_result('Concluído', True)
            self.assertTrue(all(button.isEnabled() for button in buttons))
        finally:
            overlay.deleteLater()

    def test_worker_close_request_runs_via_qt_signal(self):
        player = object.__new__(JinxUI)
        player._win = self.window
        worker = threading.Thread(target=player.request_close)
        worker.start(); worker.join(1)
        self.app.processEvents()
        self.assertFalse(self.window.isVisible())

    def test_notice_is_small_and_opens_full_text_only_when_clicked(self):
        self.fullscreen()
        text = 'Resultado com detalhes. ' * 150
        self.window._show_content('Notícias', text)
        self.assertTrue(self.window._content_panel.isHidden())
        self.assertFalse(self.mode.popup.isVisible())
        toast = next(reversed(self.mode.toasts.values()))
        self.assertLessEqual(toast.width(), 280)
        self.assertLessEqual(toast.height(), 90)
        self.assertTrue(toast.timer.isActive())
        toast.open_button.click()
        self.app.processEvents()
        self.assertTrue(self.mode.popup.isVisible())
        self.assertEqual(self.mode.popup.text.toPlainText(), text)
        self.assertEqual(self.window._hud_cam_stack.currentIndex(), 0)
        self.window._escape_display()
        self.assertFalse(self.mode.popup.isVisible())
        self.assertTrue(self.mode.active)
        self.window._escape_display()
        self.assertFalse(self.mode.active)

    def test_old_results_open_their_own_snapshot(self):
        self.fullscreen()
        self.window._show_content('Primeiro', 'Conteúdo 1')
        first = next(reversed(self.mode.entries))
        self.window._show_content('Segundo', 'Conteúdo 2')
        self.mode.open_popup(first)
        self.assertEqual(self.mode.popup.text.toPlainText(), 'Conteúdo 1')
        self.mode.open_popup('Segundo')
        self.assertEqual(self.mode.popup.text.toPlainText(), 'Conteúdo 2')

    def test_history_and_widgets_are_bounded_and_expired_toasts_still_open(self):
        self.fullscreen()
        for i in range(40): self.window._show_content(f'Resultado {i}', f'Texto {i}')
        self.assertEqual(len(self.mode.entries), self.mode.LIMIT)
        self.assertLessEqual(len(self.mode.toasts), 3)
        toast = next(reversed(self.mode.toasts.values()))
        toast.timer.timeout.emit()
        self.assertFalse(toast.isVisible())
        self.mode.open_popup(toast.key)
        self.assertTrue(self.mode.popup.isVisible())
        self.assertEqual(self.mode.popup.text.toPlainText(), 'Texto 39')

    def test_repeated_results_coalesce_and_lookup_handles_accents_and_ambiguity(self):
        self.fullscreen()
        self.window._show_content('Notícias', '1')
        self.window._show_content('Notícias', '2')
        self.assertEqual(len(self.mode.entries), 1)
        self.mode.open_popup('noticias')
        self.assertEqual(self.mode.popup.text.toPlainText(), '2')
        self.window._show_content('Notícias de jogos', '3')
        self.assertFalse(self.mode.control('open_popup', 'not')['ok'])
        self.assertFalse(self.mode.control('open_popup', 'não existe')['ok'])

    def test_quiz_popup_preserves_answers_and_returns_to_splitter(self):
        self.fullscreen()
        self.window._show_quiz('Teste', [{'question': 'Qual?', 'options': ['A', 'B'], 'answer': 'A'}])
        self.assertTrue(self.window._quiz_panel.isHidden())
        self.mode.open_popup()
        self.assertTrue(self.window._quiz_panel.isVisible())
        self.window._quiz_submit('A')
        self.assertTrue(self.window._quiz['answered'])
        self.mode.close_popup()
        self.assertEqual(self.window._center_split.indexOf(self.window._quiz_panel), 2)
        self.mode.open_popup()
        self.assertTrue(self.window._quiz['answered'])
        self.window._hide_quiz()
        self.assertIsNone(self.mode.current)
        self.assertFalse(any(r['kind'] == 'quiz' for r in self.mode.entries.values()))

    def test_confirmation_requires_the_original_human_button(self):
        self.fullscreen()
        with patch('core.confirm.resolve') as resolve:
            self.window._show_confirm_banner('Ação', 'Leia estes detalhes antes de confirmar')
            overlay = self.window._confirm_overlay
            self.assertFalse(overlay.isVisible())
            self.mode.open_popup()
            self.assertTrue(overlay.isVisible())
            resolve.assert_not_called()
            self.mode.close_popup()
            resolve.assert_not_called()
            self.mode.open_popup()
            yes = next(button for button in overlay.findChildren(QPushButton) if 'CONFIRMAR' in button.text())
            yes.click()
            resolve.assert_called_once_with(True)
            self.assertIsNone(self.window._confirm_overlay)
            self.assertIsNone(self.mode.current)

    def test_image_opens_in_popup_without_replacing_orb_and_closes_cleanly(self):
        self.fullscreen()
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'test.png')
            image = QImage(32, 32, QImage.Format.Format_RGB32)
            image.fill(QColor('#00d4ff'))
            self.assertTrue(image.save(path))
            self.window._on_image_open(path, 'Imagem')
            self.assertEqual(self.window._hud_cam_stack.currentIndex(), 0)
            self.assertFalse(self.mode.popup.isVisible())
            self.mode.open_popup()
            self.assertTrue(self.window._video_cont.isVisible())
            self.window._on_video_close()
            self.assertIsNone(self.mode.current)
            self.assertEqual(self.window._hud_cam_stack.count(), 3)
            self.assertFalse(self.window._video_on)

    def test_active_camera_notice_is_pinned_and_dismiss_stops_capture(self):
        self.fullscreen()
        self.window._on_cam_stream(True)  # No device/thread started in this test.
        key = next(reversed(self.mode.entries))
        for i in range(40): self.window._show_content(str(i), 'Resultado')
        self.assertIn(key, self.mode.toasts)
        self.assertTrue(self.mode.toasts[key].isVisible())
        self.assertFalse(self.mode.toasts[key].timer.isActive())
        self.mode.dismiss(key)
        self.assertFalse(self.window._cam_stream_active)
        self.assertTrue(self.window._cam_stop.is_set())
        self.assertNotIn(key, self.mode.entries)

    def test_recording_stop_remains_visible_in_orb_mode(self):
        self.fullscreen()
        ack = threading.Event()
        self.window._set_meeting_recording(True, ack)
        self.app.processEvents()
        self.assertTrue(ack.is_set())
        self.assertTrue(self.window._meeting_button.isVisible())
        self.assertTrue(self.window._meeting_toolbar.isVisible())

    def test_facade_and_plugin_from_worker_receive_gui_ack(self):
        self.fullscreen()
        self.window._show_content('Resultado', 'Conteúdo')
        player = object.__new__(JinxUI)
        player._win = self.window
        results = []
        worker = threading.Thread(target=lambda: results.append(display_control.run({'action': 'open_popup'}, player)))
        worker.start()
        deadline = time.monotonic() + 2
        while worker.is_alive() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.002)
        worker.join(.05)
        self.assertFalse(worker.is_alive())
        self.assertIn('status=done', results[0])
        self.assertTrue(self.mode.popup.isVisible())
        state = player.display_state()
        state['popups'].clear()
        self.assertTrue(player.display_state()['popups'])

    def test_command_box_and_enlarge_close_then_return_maximized(self):
        self.window.showMaximized()
        self.app.processEvents()
        self.fullscreen()
        self.window._show_content('Notícias', 'Texto')
        self.mode.show_command()
        self.assertTrue(self.mode.command.isVisible())
        self.mode.command.setText('abra o pop-up de notícias')
        self.mode.submit_command()
        self.assertTrue(self.mode.popup.isVisible())
        small = self.mode.popup.width()
        self.mode.control('expand_popup')
        self.assertGreaterEqual(self.mode.popup.width(), small)
        self.mode.control('windowed')
        self.app.processEvents()
        self.assertFalse(self.mode.active)
        self.assertTrue(self.window.isMaximized())


if __name__ == '__main__': unittest.main()
