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

    def test_available_styles(self):
        self.assertEqual(
            hud.HudCanvas.available_styles(), ('face', 'core', 'aurora', 'qwen_neural'))

    def test_qwen_neural_orb_is_bundled(self):
        page = hud.HudCanvas._orb_page_path('qwen_neural')
        self.assertTrue(page.is_file(), f'faltando: {page}')
        self.assertEqual(page.parent.name, 'qwen_neural')

    def test_aurora_is_a_native_style(self):
        canvas = self.canvas('aurora')
        self.assertEqual(canvas.hud_style, 'aurora')
        self.assertEqual(canvas._orb_views, {})
        canvas._sync_hud_style()
        self.assertEqual(canvas._orb_views, {})


if __name__ == '__main__':
    unittest.main()
