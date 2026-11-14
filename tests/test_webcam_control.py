import os
import threading
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtWidgets import QApplication
from gui.window import MainWindow
from ui import JinxUI


class WebcamControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        for name, value in (
            ('gui.window._read_full_config', {'assistant_name': 'JINX', 'gemini_api_key': 'fake', 'os_system': 'Windows'}),
            ('gui.window.HAVE_VIDEO', False),
            ('memory.config_manager.get_hud_style', 'face'),
        ):
            item = patch(name, value) if name.endswith('HAVE_VIDEO') else patch(name, return_value=value)
            item.start()
            self.addCleanup(item.stop)
        self.window = MainWindow('face.png')
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window._cam_worker_running = False
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_button_groups_with_mic_and_stop_and_is_hidden_in_fullscreen(self):
        self.assertTrue(self.window._webcam_button.isVisible())
        self.assertEqual(self.window._webcam_button.parentWidget(), self.window._mute_btn.parentWidget())
        self.assertLess(self.window._mute_btn.x(), self.window._webcam_button.x())
        self.assertLess(self.window._webcam_button.x(), self.window._interrupt_btn.x())
        self.window.showFullScreen()
        self.app.processEvents()
        self.assertTrue(self.window._orb_mode.active)
        self.assertFalse(self.window._webcam_button.isVisible())
        self.window.showNormal()
        self.app.processEvents()
        self.assertTrue(self.window._webcam_button.isVisible())
        with patch('gui.window.threading.Thread') as thread:
            self.window._webcam_button.click()
            self.assertIn('CANCELAR', self.window._webcam_button.text())
            self.window.start_camera_stream()
            thread.assert_called_once()
            self.window._webcam_button.click()
            self.assertTrue(self.window._cam_stop.is_set())
            self.assertFalse(self.window._webcam_button.isEnabled())
        self.window._cam_worker_running = False
        self.window._on_cam_stream(False)
        self.assertTrue(self.window._webcam_button.isEnabled())
        self.assertFalse(self.window._webcam_button.isChecked())

    def test_explicit_button_request_opens_camera_popup_and_stop_closes_it(self):
        self.window.showFullScreen()
        self.app.processEvents()
        self.window._cam_preview_requested = True
        self.window._on_cam_stream(True)
        self.assertTrue(self.window._cam_cont.isVisible())
        self.assertTrue(self.window._webcam_button.isChecked())
        self.window._webcam_button.click()
        self.assertFalse(self.window._cam_stream_active)
        self.assertFalse(self.window._webcam_button.isChecked())
        self.assertIsNone(self.window._orb_mode.current)

    def test_missing_device_releases_both_handles_and_reports_failure(self):
        import cv2
        first, second = Mock(), Mock()
        first.isOpened.return_value = second.isOpened.return_value = False
        self.window._cam_worker_running = True
        with patch.object(cv2, 'VideoCapture', side_effect=[first, second]):
            self.window._cam_loop()
        first.release.assert_called_once()
        second.release.assert_called_once()
        self.assertFalse(self.window._cam_worker_running)
        self.assertFalse(self.window._webcam_button.isChecked())
        self.assertIn('WEBCAM INDISPONÍVEL', self.window._content_title_lbl.text())

    def test_continuous_frames_end_only_at_stop_and_release_device(self):
        import cv2
        import numpy as np
        cap = Mock()
        cap.isOpened.return_value = True
        cap.read.return_value = True, np.zeros((24, 32, 3), dtype=np.uint8)
        callback = Mock()
        self.window.on_camera_frame = callback
        self.window.on_camera_stopped = Mock()
        self.window._cam_worker_running = True
        original = self.window._cam_stop
        stop = Mock()
        stop.is_set.return_value = False
        stop.wait.side_effect = [False, False, True]
        self.window._cam_stop = stop
        try:
            with patch.object(cv2, 'VideoCapture', return_value=cap):
                self.window._cam_loop()
        finally:
            self.window._cam_stop = original
        self.assertEqual(callback.call_count, 2)
        self.window.on_camera_stopped.assert_called_once()
        cap.release.assert_called_once()
        self.assertFalse(self.window._cam_worker_running)
        self.assertFalse(self.window._cam_stream_active)

    def test_worker_facade_queues_start_without_touching_widgets(self):
        facade = JinxUI.__new__(JinxUI)
        facade._win = self.window
        with patch.object(self.window, '_cam_loop') as loop:
            worker = threading.Thread(target=facade.start_camera_stream)
            worker.start()
            worker.join(timeout=2)
            self.assertFalse(worker.is_alive())
            self.assertFalse(self.window._cam_worker_running)
            self.app.processEvents()
            # Qt dispatches the start; it alone launches the capture worker.
            for _ in range(10):
                self.app.processEvents()
                if loop.called:
                    break
            self.assertTrue(loop.called)

    def test_gestures_show_persistent_stop_and_do_not_start_when_runtime_missing(self):
        from core.gesture_control import control
        with patch.object(control, 'status', return_value={'active': False}), \
                patch.object(control, 'start', return_value=(False, 'Instale o suporte')), \
                patch.object(self.window, 'start_camera_stream') as camera:
            self.window._toggle_gestures(True)
        camera.assert_not_called()
        self.window._on_gesture_state('Abra a pinça para armar')
        self.assertTrue(self.window._gesture_stop_btn.isVisible())
        with patch.object(control, 'stop') as stop:
            self.window._gesture_stop_btn.click()
        stop.assert_called_once()
        self.window._on_gesture_state('Gestos desligados')
        self.assertFalse(self.window._gesture_toolbar.isVisible())
