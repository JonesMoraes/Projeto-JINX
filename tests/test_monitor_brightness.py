import unittest
from contextlib import contextmanager
from unittest.mock import Mock, patch
from core import undo
from actions import monitor_brightness as b


class BrightnessTest(unittest.TestCase):
    def setUp(self):
        undo.clear()
        self.addCleanup(undo.clear)
        self.values = {"A": 50, "B": 60}
        client = Mock()
        @contextmanager
        def connection():
            yield client
        p = patch.object(b, "connection", connection)
        p.start(); self.addCleanup(p.stop)
        p = patch.object(b, "monitors", side_effect=lambda _: dict(self.values))
        p.start(); self.addCleanup(p.stop)
        def set_one(_, name, value):
            self.values[name] = value
            return True
        p = patch.object(b, "set_one", side_effect=set_one)
        self.setter = p.start(); self.addCleanup(p.stop)

    def test_exact_target_readback_and_undo(self):
        self.assertIn("status=done", b.run({"action": "set", "monitor": "A", "percent": 30}))
        self.assertEqual(self.values, {"A": 30, "B": 60})
        undo.undo_last()
        self.assertEqual(self.values["A"], 50)

    def test_ambiguous_invalid_and_disconnected(self):
        for p in ({"percent": 20}, {"monitor": "C", "percent": 20}, {"monitor": "A", "percent": True}, {"monitor": "A", "percent": 101}):
            self.assertIn("status=failed", b.run({"action": "set", **p}))
        self.setter.assert_not_called()

    def test_readback_not_success_and_no_undo(self):
        self.setter.side_effect = None
        self.setter.return_value = False
        self.assertIn("status=unverified", b.run({"action": "set", "monitor": "A", "percent": 30}))
        self.assertFalse(undo.can_undo())

    def test_undo_does_not_override_user_change(self):
        b.run({"action": "set", "monitor": "A", "percent": 30})
        self.values["A"] = 40
        self.assertIn("status=failed", undo.undo_last())
        self.assertEqual(self.values["A"], 40)

    def test_no_monitors(self):
        self.values.clear()
        self.assertIn("status=unverified", b.run({"action": "list"}))
