"""Qt main-thread tests: native startup never instantiates Chromium."""
import os
import unittest
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
            for style in ('face', 'core'):
                canvas = self.canvas(style)
                self.assertEqual(canvas.hud_style, style)
                self.assertEqual(canvas._orb_views, {})
        create.assert_not_called()

    def test_unavailable_saved_web_style_falls_back_without_changing_config(self):
        with patch.object(hud, 'QWebEngineView', None), \
                patch('memory.config_manager.save_hud_style') as save:
            self.assertEqual(hud.HudCanvas.available_styles(), ('face', 'core'))
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


if __name__ == '__main__': unittest.main()
