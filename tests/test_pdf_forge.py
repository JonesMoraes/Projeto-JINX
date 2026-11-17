from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader
from reportlab.pdfgen import canvas

from actions.pdf_forge import pdf_forge
from core import undo


def make_pdf(path: Path, pages: int, label: str) -> None:
    doc = canvas.Canvas(str(path))
    for number in range(pages):
        doc.drawString(80, 750, f"{label} page {number + 1}")
        doc.showPage()
    doc.save()


class PdfForgeTests(unittest.TestCase):
    def setUp(self):
        undo.clear()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(undo.clear)
        self.root = Path(self.temp.name)
        self.one = self.root / "one.pdf"
        self.two = self.root / "two.pdf"
        make_pdf(self.one, 2, "alpha")
        make_pdf(self.two, 1, "beta")

    def test_create_and_extract_searchable_text(self):
        output = self.root / "created.pdf"
        result = pdf_forge({"action": "create", "title": "Report", "text": "Hello JINX",
                            "output_path": str(output)})
        self.assertIn("status=done", result)
        self.assertEqual(len(PdfReader(output).pages), 1)
        extracted = pdf_forge({"action": "extract_text", "file_path": str(output)})
        self.assertIn("Hello JINX", extracted)

    def test_merge_and_split_verify_pages(self):
        merged = self.root / "merged.pdf"
        result = pdf_forge({"action": "merge", "files": [str(self.one), str(self.two)],
                            "output_path": str(merged)})
        self.assertIn("status=done", result)
        self.assertEqual(len(PdfReader(merged).pages), 3)
        output_dir = self.root / "split"
        split = pdf_forge({"action": "split", "file_path": str(merged),
                           "output_dir": str(output_dir)})
        self.assertIn("status=done", split)
        self.assertEqual(len(list(output_dir.glob("*.pdf"))), 3)

    def test_cover_adds_one_page_without_touching_source(self):
        output = self.root / "covered.pdf"
        result = pdf_forge({"action": "cover", "file_path": str(self.one),
                            "title": "Cover", "output_path": str(output)})
        self.assertIn("status=done", result)
        self.assertEqual(len(PdfReader(self.one).pages), 2)
        self.assertEqual(len(PdfReader(output).pages), 3)

    def test_output_collision_does_not_overwrite(self):
        result = pdf_forge({"action": "merge", "files": [str(self.one), str(self.two)],
                            "output_path": str(self.one)})
        self.assertIn("status=failed", result)
        self.assertEqual(len(PdfReader(self.one).pages), 2)


if __name__ == "__main__":
    unittest.main()
