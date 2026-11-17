from __future__ import annotations

import unittest
from unittest.mock import patch

from actions import process_manager as manager
from core import undo


class FakeProcess:
    def __init__(self):
        self.priority = 5
        self.affinity = [0, 1]

    def nice(self, value=None):
        if value is not None:
            self.priority = value
        return self.priority

    def cpu_affinity(self, value=None):
        if value is not None:
            self.affinity = list(value)
        return list(self.affinity)


class ProcessControlTests(unittest.TestCase):
    def setUp(self):
        undo.clear()
        self.addCleanup(undo.clear)
        self.process = FakeProcess()
        self.target = manager.Target(999999, 1.0, "sample", "sample.exe")
        patcher = patch.object(manager, "_guard", return_value=self.process)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_priority_change_and_undo(self):
        with patch.object(manager.platform, "system", return_value="Linux"):
            self.assertIn("status=done", manager._set_priority(self.target, 12))
            self.assertEqual(self.process.priority, 12)
            self.assertIn("status=done", undo.undo_last())
            self.assertEqual(self.process.priority, 5)

    def test_affinity_change_and_undo(self):
        self.assertIn("status=done", manager._set_affinity(self.target, [1]))
        self.assertEqual(self.process.affinity, [1])
        self.assertIn("status=done", undo.undo_last())
        self.assertEqual(self.process.affinity, [0, 1])

    def test_affinity_rejects_duplicate_or_invalid_indexes(self):
        self.assertIn("status=failed", manager._set_affinity(self.target, [0, 0]))
        self.assertIn("status=failed", manager._set_affinity(self.target, [-1]))
        self.assertEqual(self.process.affinity, [0, 1])


if __name__ == "__main__":
    unittest.main()
