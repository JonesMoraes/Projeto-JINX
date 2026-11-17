from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from actions.fs_total import fs_total
from core import undo


class FsTotalTests(unittest.TestCase):
    def setUp(self):
        undo.clear()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(undo.clear)
        self.root = Path(self.temp.name)

    def test_write_read_append_and_undo(self):
        path = self.root / "nested" / "file.txt"
        self.assertIn("status=done", fs_total({"action": "write", "path": str(path),
                                               "content": "first"}))
        self.assertIn("first", fs_total({"action": "read", "path": str(path)}))
        fs_total({"action": "append", "path": str(path), "content": " second"})
        self.assertEqual(path.read_text(encoding="utf-8"), "first second")
        self.assertIn("status=done", undo.undo_last())
        self.assertEqual(path.read_text(encoding="utf-8"), "first")

    def test_delete_is_recoverable(self):
        path = self.root / "erase.txt"
        path.write_text("recover", encoding="utf-8")
        result = fs_total({"action": "delete", "path": str(path)})
        self.assertIn("status=done", result)
        self.assertFalse(path.exists())
        self.assertIn("status=done", undo.undo_last())
        self.assertEqual(path.read_text(encoding="utf-8"), "recover")

    def test_copy_and_move_refuse_overwrite(self):
        source = self.root / "source.txt"
        dest = self.root / "dest.txt"
        source.write_text("data", encoding="utf-8")
        dest.write_text("keep", encoding="utf-8")
        self.assertIn("status=failed", fs_total({"action": "copy", "path": str(source),
                                                 "destination": str(dest)}))
        self.assertEqual(dest.read_text(encoding="utf-8"), "keep")

    def test_permission_change_and_undo(self):
        path = self.root / "mode.txt"
        path.write_text("x", encoding="utf-8")
        # 0444 is portable: Windows represents read-only via its DOS attribute.
        result = fs_total({"action": "chmod", "path": str(path), "mode": "444"})
        self.assertIn("status=done", result)
        self.assertIn("status=done", undo.undo_last())


if __name__ == "__main__":
    unittest.main()
