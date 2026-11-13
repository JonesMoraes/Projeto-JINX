import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from core import office, undo
from plugins import office_suite


class OfficeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        p = patch.object(office, "destination", return_value=Path(self.temp.name)); p.start(); self.addCleanup(p.stop)
        undo.clear(); self.addCleanup(undo.clear)

    def test_five_slides_reopen_and_notes(self):
        from pptx import Presentation
        data = {"title": "Teste", "slides": [{"title": str(i), "bullets": ["Texto PT-BR"], "notes": "Notas " + str(i)} for i in range(5)]}
        with patch.object(office.gemini, "as_json", return_value=data) as ladder:
            result = office_suite.run({"action": "create", "format": "pptx", "topic": "Eletrônica", "count": 5})
        self.assertIn("status=done", result)
        files = list(Path(self.temp.name).glob("*.pptx")); self.assertEqual(len(files), 1)
        deck = Presentation(files[0]); self.assertEqual(len(deck.slides), 5)
        self.assertEqual(deck.slides[4].notes_slide.notes_text_frame.text, "Notas 4")
        self.assertIn("<<<UNTRUSTED", ladder.call_args.args[0])

    def test_docx_headings_bullets_table(self):
        from docx import Document
        raw = office.generate("docx", {"title": "Relatório", "blocks": [{"heading": "Dados", "text": "Olá", "bullets": ["A"], "table": [["Item", "Valor"], ["A", "10"]]}]})
        doc = Document(io.BytesIO(raw)); self.assertEqual(len(doc.tables), 1)
        self.assertEqual(doc.tables[0].cell(1, 1).text, "10")

    def test_xlsx_real_formula_and_external_ref_refusal(self):
        from openpyxl import load_workbook
        raw = office.generate("xlsx", {"sheets": [{"name": "Dados", "rows": [["Valor"], [10], [20], ["=SUM(A2:A3)"]]}]})
        doc = load_workbook(io.BytesIO(raw)); self.assertEqual(doc.active["A4"].value, "=SUM(A2:A3)"); doc.close()
        with self.assertRaises(ValueError): office.generate("xlsx", {"sheets": [{"name": "X", "rows": [['=WEBSERVICE("https://example.com")']]}]})

    def test_undo_preserves_modified_and_never_overwrites(self):
        path = Path(office.created(b"original", ".txt", "same"))
        second = Path(office.created(b"second", ".txt", "same"))
        self.assertNotEqual(path, second)
        undo.undo_last(); self.assertFalse(second.exists())
        path.write_bytes(b"edited")
        self.assertIn("status=failed", undo.undo_last()); self.assertEqual(path.read_bytes(), b"edited")

    def test_model_failure_creates_nothing(self):
        with patch.object(office.gemini, "as_json", return_value=None):
            self.assertIn("status=failed", office_suite.run({"action": "create", "format": "pptx", "topic": "X"}))
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_pdf_real_merge_and_split(self):
        office.dependency("pypdf")
        from pypdf import PdfWriter, PdfReader
        source = Path(self.temp.name) / "source.pdf"
        writer = PdfWriter(); writer.add_blank_page(width=100, height=100); writer.add_blank_page(width=100, height=100)
        with source.open("wb") as f: writer.write(f)
        merged = office.pdf({"action": "merge", "files": [str(source), str(source)]})
        self.assertEqual(len(PdfReader(merged).pages), 4)
        split = office.pdf({"action": "split", "files": [merged], "pages": [4, 2]})
        self.assertEqual(len(PdfReader(split).pages), 2)
        with self.assertRaises(ValueError): office.pdf({"action": "split", "files": [str(source)], "pages": [0]})
        self.assertIsInstance(office.pdf({"action": "extract", "files": [str(source)]}), str)

    def test_conversion_requires_real_converter(self):
        with patch.object(office.shutil, "which", return_value=None), patch.object(Path, "is_file", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "LibreOffice"): office.convert({"files": ["x.docx"]})
