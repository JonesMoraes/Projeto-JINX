import json
import math
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, MagicMock, patch
from email.message import Message

from core.pinch_pointer import PinchPointer
from core.gesture_control import GestureControl
from core import gesture_install
from plugins import gesture_control as plugin


def hand(gap=.25, x=.5):
    points = [[.5, .5] for _ in range(21)]
    points[5], points[17] = [.35, .65], [.65, .65]
    points[8], points[4] = [x, .4], [x + gap, .4]
    return points


class PinchTests(unittest.TestCase):
    def setUp(self):
        self.mouse = Mock()
        self.mouse.size.return_value = 1920, 1080
        self.pointer = PinchPointer(self.mouse)

    def arm_and_grab(self):
        self.pointer.update(hand(), 0)
        self.pointer.update(hand(), .31)
        self.pointer.update(hand(.01), .4)
        self.pointer.update(hand(.01), .6)

    def test_open_arm_sustained_pinch_drag_release(self):
        self.arm_and_grab()
        self.mouse.down.assert_called_once()
        previous_x = self.mouse.move.call_args.args[0]
        self.pointer.update(hand(.01, .6), .7)
        self.assertTrue(self.pointer.pressed)
        self.assertLess(self.mouse.move.call_args.args[0], previous_x)
        self.pointer.update(hand(), .8)
        self.mouse.up.assert_called_once()
        self.assertFalse(self.pointer.pressed)

    def test_closed_hand_cannot_grab_on_activation_or_after_tracking_loss(self):
        for now in (0, 1, 2): self.pointer.update(hand(.01), now)
        self.mouse.down.assert_not_called()
        self.arm_and_grab()
        self.pointer.update([], 1)
        self.mouse.up.assert_called_once()
        self.pointer.update(hand(.01), 2)
        self.pointer.update(hand(.01), 3)
        self.mouse.down.assert_called_once()
        self.assertFalse(self.pointer.armed)

    def test_hysteresis_prevents_drag_flicker(self):
        self.arm_and_grab()
        self.pointer.update(hand(.12), .7)
        self.assertTrue(self.pointer.pressed)
        self.mouse.up.assert_not_called()
        self.pointer.update(hand(), .8)
        self.mouse.up.assert_called_once()

    def test_short_pinch_does_not_press(self):
        self.pointer.update(hand(), 0)
        self.pointer.update(hand(), .31)
        self.pointer.update(hand(.01), .4)
        self.pointer.update(hand(), .5)
        self.mouse.down.assert_not_called()

    def test_invalid_or_small_landmarks_release_without_cursor_motion(self):
        for points in ([], [[math.nan, .5]] * 21, [[2, .5]] * 21, [[.5, .5]] * 21):
            self.arm_and_grab()
            self.mouse.reset_mock()
            self.pointer.update(points, 2)
            self.mouse.up.assert_called_once()
            self.mouse.move.assert_not_called()


class ControllerTests(unittest.TestCase):
    def controller(self):
        ctrl = GestureControl()
        mouse = Mock()
        mouse.size.return_value = 1920, 1080
        mouse.emergency.return_value = False
        ctrl.pointer = PinchPointer(mouse)
        ctrl.pointer.pressed = True
        ctrl.running = True
        return ctrl, mouse

    def test_stop_releases_pressed_mouse_and_terminates_tracker(self):
        ctrl, mouse = self.controller()
        ctrl.process = Mock()
        ctrl.process.poll.return_value = None
        ctrl.stop()
        mouse.up.assert_called_once()
        ctrl.process.terminate.assert_called_once()
        self.assertTrue(ctrl.stop_event.is_set())

    def test_global_emergency_key_stops_without_qt_focus(self):
        ctrl, mouse = self.controller()
        mouse.emergency.return_value = True
        ctrl._watch()
        self.assertTrue(ctrl.stop_event.is_set())
        mouse.up.assert_called_once()

    def test_stalled_inference_releases_drag_and_requires_rearming(self):
        ctrl, mouse = self.controller()
        ctrl.last_result = time.monotonic() - 1
        ctrl.stop_event = Mock()
        ctrl.stop_event.wait.side_effect = [False, True]
        ctrl._watch()
        mouse.up.assert_called_once()
        self.assertFalse(ctrl.pointer.armed)

    def test_missing_runtime_never_starts_or_controls_mouse(self):
        ctrl = GestureControl()
        with patch('core.gesture_control.PYTHON') as python:
            python.is_file.return_value = False
            with patch('core.gesture_control.WindowsMouse') as mouse:
                ok, _ = ctrl.start(Mock())
        self.assertFalse(ok)
        mouse.assert_not_called()
        self.assertFalse(ctrl.status()['active'])

    def test_disabled_feed_ignores_frames(self):
        ctrl = GestureControl()
        ctrl.feed(None)
        self.assertTrue(ctrl.frames.empty())


class PluginAndInstallerTests(unittest.TestCase):
    def test_prepare_checks_size_and_duplicate_model_hash_headers_without_downloading(self):
        manifest = json.loads(gesture_install.MANIFEST.read_text(encoding='utf-8'))
        sizes = {p['url']: p['size'] for p in manifest['packages']}
        sizes[gesture_install.MODEL_URL] = manifest['model_size']
        replies = []
        def head(request, **kwargs):
            self.assertEqual(request.get_method(), 'HEAD')
            response = MagicMock()
            response.__enter__.return_value = response
            headers = Message()
            headers['Content-Length'] = str(sizes[request.full_url])
            if request.full_url == gesture_install.MODEL_URL:
                headers['x-goog-hash'] = 'crc32c=example'
                headers['x-goog-hash'] = 'md5=' + manifest['model_md5']
            response.headers = headers
            replies.append(response)
            return response
        with patch.object(gesture_install.urllib.request, 'urlopen', side_effect=head), \
                patch.object(gesture_install.subprocess, 'run') as process:
            plan = gesture_install.prepare()
        self.assertEqual(plan['bytes'], manifest['bytes'])
        process.assert_not_called()
        for response in replies: response.read.assert_not_called()

    def test_no_hud_cannot_enable_mouse(self):
        result = plugin.run({'action': 'start'}, player=None)
        self.assertIn('failed', result)

    def test_start_only_requests_qt_action_and_stop_is_direct(self):
        player = Mock()
        self.assertIn('started', plugin.run({'action': 'start'}, player))
        player.toggle_gestures.assert_called_once_with(True)
        with patch.object(plugin.control, 'stop') as stop:
            plugin.run({'action': 'stop'}, player)
        stop.assert_called_once()

    def test_large_install_cannot_run_without_explicit_approval(self):
        with patch.object(gesture_install.subprocess, 'run') as env:
            ok, _ = gesture_install.install({'bytes': 100 * 1048576})
        self.assertFalse(ok)
        env.assert_not_called()

    def test_settings_prepare_review_without_installing_or_enabling(self):
        with patch('core.gesture_install.prepare', return_value={'bytes': 100 * 1048576}), \
                patch('core.confirm.pending_title', return_value=''), \
                patch('core.confirm.request', return_value='pending') as confirm, \
                patch('core.gesture_install.install') as install:
            ok, message = plugin.prepare_install({})
        self.assertTrue(ok)
        self.assertIn('100.0 MB', confirm.call_args.args[1])
        install.assert_not_called()


if __name__ == '__main__': unittest.main()
