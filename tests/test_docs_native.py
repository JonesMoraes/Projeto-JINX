from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook, load_workbook

from actions.docs_native import docs_native
from core import undo


class DocsNativeTests(unittest.TestCase):
    def setUp(self):
        undo.clear()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(undo.clear)
        self.source = Path(self.temp.name) / "source.xlsx"
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Dados"
        sheet["A1"] = "old"
        sheet["B1"] = "=1+1"
        workbook.save(self.source)

    def test_cell_range_edit_preserves_source_and_formula(self):
        result = docs_native({"action": "write_cells", "file_path": str(self.source),
                              "sheet": "Dados", "cell_range": "A1:A2",
                              "values": [["new"], [12]]})
        self.assertIn("status=done", result)
        output = Path(result.split("output=")[1].split(" verified=")[0].strip('"'))
        self.assertTrue(output.is_file())
        original = load_workbook(self.source, data_only=False)
        edited = load_workbook(output, data_only=False)
        try:
            self.assertEqual(original["Dados"]["A1"].value, "old")
            self.assertEqual(original["Dados"]["B1"].value, "=1+1")
            self.assertEqual(edited["Dados"]["A1"].value, "new")
            self.assertEqual(edited["Dados"]["A2"].value, 12)
            self.assertEqual(edited["Dados"]["B1"].value, "=1+1")
        finally:
            original.close()
            edited.close()

    def test_invalid_dimensions_and_missing_sheet_do_not_create_output(self):
        base = {"action": "write_cells", "file_path": str(self.source),
                "sheet": "Dados", "cell_range": "A1:B2", "values": [["too small"]]}
        self.assertIn("status=failed", docs_native(base))
        self.assertEqual(list(Path(self.temp.name).glob("*-jinx-edited*.xlsx")), [])

    def test_read_range_returns_existing_cell_values(self):
        result = docs_native({"action": "read", "file_path": str(self.source),
                              "sheet": "Dados", "cell_range": "A1:B1"})
        self.assertIn("status=done", result)
        self.assertIn("old", result)
        self.assertIn("=1+1", result)


if __name__ == "__main__":
    unittest.main()
