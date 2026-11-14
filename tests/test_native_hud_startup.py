"""Qt main-thread tests: native startup never instantiates Chromium."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtWidgets import QApplication
from gui import hud


class NativeHudTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def canvas(self, style):
        with patch('memory.config_manager.get_hud_style', return_value=style):
            canvas = hud.HudCanvas('face.png')
        self.addCleanup(canvas.deleteLater)
        return canvas

    def test_native_startup_does_not_construct_hidden_web_views(self):
        create = Mock(side_effect=AssertionError('WebEngine must not start for native HUD'))
        with patch.object(hud, 'QWebEngineView', create):
            for style in ('face', 'core', 'aurora'):
                canvas = self.canvas(style)
                self.assertEqual(canvas.hud_style, style)
                self.assertEqual(canvas._orb_views, {})
        create.assert_not_called()

    def test_unavailable_saved_web_style_falls_back_without_changing_config(self):
        with patch.object(hud, 'QWebEngineView', None), \
                patch('memory.config_manager.save_hud_style') as save:
            self.assertEqual(hud.HudCanvas.available_styles(), ('face', 'core', 'aurora'))
            canvas = self.canvas('brahma_evo')
            self.assertEqual(canvas.hud_style, 'face')
            self.assertEqual(canvas._orb_views, {})
        save.assert_not_called()

    def test_disabled_web_views_never_start_downloads(self):
        with patch.object(hud, 'QWebEngineView', None), \
                patch.object(hud.HudCanvas, '_start_evo_download') as download:
            canvas = self.canvas('brahma_evo')
            canvas._sync_hud_style()
        download.assert_not_called()

    def test_selected_web_sphere_is_created_lazily_and_loads_existing_asset(self):
        with tempfile.TemporaryDirectory() as folder:
            page = Path(folder) / 'index.html'
            page.write_text('<html><body>Test fixture</body></html>', encoding='utf-8')
            with patch.object(hud.HudCanvas, '_orb_page_path', return_value=page):
                self._check_selected_web_spheres()

    def _check_selected_web_spheres(self):
        for style in ('brahma_evo', 'brahma_echo'):
            view = Mock()
            with patch.object(hud, 'QWebEngineView', return_value=view) as create, \
                    patch.object(hud, 'QWebEngineSettings', None):
                canvas = self.canvas(style)
                self.assertEqual(canvas.hud_style, style)
                create.assert_called_once_with(canvas)
                view.setUrl.assert_called_once()
                self.assertTrue(view.setUrl.call_args.args[0].isLocalFile())
                canvas._sync_hud_style()
                create.assert_called_once()

    def test_missing_assets_show_notice_without_network_in_test(self):
        with tempfile.TemporaryDirectory() as folder:
            missing = Path(folder) / 'missing.html'
            for style in ('brahma_evo', 'brahma_echo'):
                view = Mock()
                with patch.object(hud, 'QWebEngineView', return_value=view), \
                        patch.object(hud, 'QWebEngineSettings', None), \
                        patch.object(hud.HudCanvas, '_orb_page_path', return_value=missing), \
                        patch.object(hud.HudCanvas, '_start_evo_download') as download:
                    canvas = self.canvas(style)
                    canvas._sync_hud_style()
                    view.setUrl.assert_not_called()
                    view.setHtml.assert_called_once()
                    self.assertEqual(download.call_count, int(style == 'brahma_evo'))

    def test_web_failure_returns_to_native_without_overwriting_preference(self):
        canvas = self.canvas('face')
        for style in ('brahma_evo', 'brahma_echo'):
            view = Mock()
            canvas._orb_views = {style: view}
            canvas.hud_style = style
            messages = []
            canvas.visual_failed.connect(messages.append)
            with patch('memory.config_manager.save_hud_style') as save:
                canvas._on_orb_loaded(style, False)
            self.assertEqual(canvas.hud_style, 'face')
            self.assertTrue(messages)
            view.setVisible.assert_called_with(False)
            save.assert_not_called()

    def test_unavailable_webgl_falls_back_but_late_callbacks_do_not_change_new_selection(self):
        canvas = self.canvas('face')
        view = Mock()
        view._jinx_orb_loaded_once = True
        canvas._orb_views = {'brahma_evo': view}
        canvas.hud_style = 'brahma_evo'
        canvas._on_orb_loaded('brahma_evo', True)
        callback = view.page.return_value.runJavaScript.call_args.args[1]
        callback(False)
        self.assertEqual(canvas.hud_style, 'face')
        canvas.hud_style = 'core'
        callback(False)
        self.assertEqual(canvas.hud_style, 'core')


if __name__ == '__main__': unittest.main()
