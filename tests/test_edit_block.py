from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from actions.edit_block import edit_block
from core import undo


class EditBlockTests(unittest.TestCase):
    def setUp(self):
        undo.clear()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(undo.clear)
        self.path = Path(self.temp.name) / "sample.txt"

    def call_edit(self, find="old", replace="new", expected=1):
        return edit_block({"path": str(self.path), "find": find, "replace": replace,
                           "expected_replacements": expected})

    def test_exact_replacement_and_undo(self):
        self.path.write_text("before old after", encoding="utf-8")
        result = self.call_edit()
        self.assertIn("status=done", result)
        self.assertEqual(self.path.read_text(encoding="utf-8"), "before new after")
        self.assertIn("status=done", undo.undo_last())
        self.assertEqual(self.path.read_text(encoding="utf-8"), "before old after")

    def test_ambiguous_match_is_refused_without_writing(self):
        self.path.write_text("old old", encoding="utf-8")
        result = self.call_edit()
        self.assertIn("status=failed", result)
        self.assertEqual(self.path.read_text(encoding="utf-8"), "old old")

    def test_unexpected_count_is_refused(self):
        self.path.write_text("old old", encoding="utf-8")
        result = self.call_edit(expected=1)
        self.assertIn("status=failed", result)
        self.assertEqual(self.path.read_text(encoding="utf-8"), "old old")

    def test_missing_match_is_refused(self):
        self.path.write_text("unchanged", encoding="utf-8")
        self.assertIn("status=failed", self.call_edit())
        self.assertEqual(self.path.read_text(encoding="utf-8"), "unchanged")

    def test_undo_does_not_overwrite_a_later_edit(self):
        self.path.write_text("old", encoding="utf-8")
        self.assertIn("status=done", self.call_edit())
        self.path.write_text("later edit", encoding="utf-8")
        self.assertIn("status=failed", undo.undo_last())
        self.assertEqual(self.path.read_text(encoding="utf-8"), "later edit")


if __name__ == "__main__":
    unittest.main()
