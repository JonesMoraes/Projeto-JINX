from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from actions.search_scale import search_scale


def result_rows(result: str) -> list[str]:
    match = re.search(r"<<<UNTRUSTED source=local-search-results>>>\s*(.*?)\s*<<<END UNTRUSTED>>>",
                      result, re.S)
    if not match:
        raise AssertionError(result)
    return match.group(1).split(" ; ") if match.group(1) != "No matches." else []


class SearchScaleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "a.txt").write_text("needle\nother\nneedle here\n", encoding="utf-8")
        (self.root / "b.txt").write_text("needle two\n", encoding="utf-8")
        (self.root / "skip.pyc").write_bytes(b"\xff\xfe\x00")

    def test_content_search_paginates_without_duplicates(self):
        first = search_scale({"root": str(self.root), "query": "needle", "page_size": 2})
        self.assertIn("status=done", first)
        self.assertIn("next_cursor=2", first)
        rows = result_rows(first)
        second = search_scale({"root": str(self.root), "query": "needle",
                               "page_size": 2, "cursor": 2})
        self.assertIn("status=done", second)
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(result_rows(second)), 1)

    def test_filename_glob_search(self):
        result = search_scale({"root": str(self.root), "filename_pattern": "*.txt"})
        rows = result_rows(result)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row.split(" | ", 1)[0].endswith(".txt") for row in rows))

    def test_invalid_pagination_and_empty_query_fail(self):
        self.assertIn("status=failed", search_scale({"root": str(self.root), "query": "x",
                                                    "page_size": 0}))
        self.assertIn("status=failed", search_scale({"root": str(self.root)}))

    def test_python_fallback_works_without_ripgrep(self):
        with patch("actions.search_scale.shutil.which", return_value=None):
            result = search_scale({"root": str(self.root), "query": "needle"})
        self.assertIn("status=done", result)
        self.assertIn("count=3", result)


if __name__ == "__main__":
    unittest.main()
