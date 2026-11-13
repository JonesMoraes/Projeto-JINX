"""Small structured Office generators and PDF tools. Optional imports on demand."""
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from core import gemini, outcome, undo
from memory.config_manager import get_plugin_config


def dependency(name):
    if importlib.util.find_spec(name) is None:
        raise RuntimeError("Dependência opcional ausente; instale em configurações / Optional dependency missing; install in settings: " + name)


def destination():
    return Path(get_plugin_config("office_suite").get("output_dir") or Path.home() / "Documents/JINX").expanduser().resolve()


def created(data, extension, title, folder=None):
    folder = Path(folder or destination()).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    name = re.sub(r'[^\w .-]', '_', str(title))[:70].strip(" .") or "JINX"
    path = folder / (name + "-" + uuid.uuid4().hex[:10] + extension)
    with path.open("xb") as handle:
        handle.write(data); handle.flush(); os.fsync(handle.fileno())
    digest = hashlib.sha256(data).hexdigest()
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise RuntimeError("File readback failed")
    def restore():
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            return outcome.failed("created_file_undo", "Arquivo mudou/ausente; preservado / File changed/missing; preserved")
        path.unlink()
        return outcome.done("created_file_undo", absent=not path.exists())
    undo.push_undo("Arquivo criado / Created file: " + path.name, restore)
    return str(path)


def content(p):
    supplied = p.get("content")
    if supplied:
        data = json.loads(supplied) if isinstance(supplied, str) else supplied
    else:
        count = int(p.get("count", 5))
        if not 1 <= count <= 30:
            raise ValueError("count 1–30")
        schema = {"pptx": '{"title":"...","slides":[{"title":"...","bullets":["..."],"notes":"...","layout":"content"}]}',
                  "docx": '{"title":"...","blocks":[{"heading":"...","text":"...","bullets":["..."],"table":[["..."]]}]}',
                  "xlsx": '{"title":"...","sheets":[{"name":"Dados","rows":[["Item","Valor"],["A",10],["Total","=SUM(B2:B2)"]]}]}'}
        topic = str(p.get("topic") or "").strip()
        if not topic:
            raise ValueError("Topic or structured content required")
        data = gemini.as_json("Create useful, accurate document content in the user's language, with " + str(count) +
            " slides if a presentation. Return JSON only matching " + schema[p["format"]] +
            ". Never invent citations; formulas must reference actual cells.\nTopic data:\n" + outcome.untrusted("document-topic", topic),
            tier=gemini.SMART, timeout_ms=30000)
    if not isinstance(data, dict):
        raise ValueError("No valid document content generated")
    return data


def generate(kind, data):
    buffer = io.BytesIO()
    if kind == "pptx":
        dependency("pptx")
        from pptx import Presentation
        doc = Presentation()
        slides = data["slides"]
        if not 1 <= len(slides) <= 30:
            raise ValueError("Slide limit")
        for item in slides:
            slide = doc.slides.add_slide(doc.slide_layouts[0 if item.get("layout") == "title" else 1])
            slide.shapes.title.text = str(item["title"])
            frame = slide.placeholders[1].text_frame
            frame.clear()
            for index, bullet in enumerate(item.get("bullets", [])[:20]):
                paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
                paragraph.text = str(bullet)
            slide.notes_slide.notes_text_frame.text = str(item.get("notes", ""))
        doc.save(buffer)
        buffer.seek(0)
        if len(Presentation(buffer).slides) != len(slides):
            raise RuntimeError("Invalid presentation")
    elif kind == "docx":
        dependency("docx")
        from docx import Document
        doc = Document()
        doc.add_heading(str(data.get("title", "JINX")), 0)
        for block in data["blocks"][:200]:
            if block.get("heading"): doc.add_heading(str(block["heading"]), 1)
            if block.get("text"): doc.add_paragraph(str(block["text"]))
            for bullet in block.get("bullets", [])[:100]: doc.add_paragraph(str(bullet), style="List Bullet")
            rows = block.get("table", [])
            if rows:
                columns = max(len(r) for r in rows)
                if columns > 30 or len(rows) > 500: raise ValueError("Table limit")
                table = doc.add_table(rows=0, cols=columns)
                table.style = "Table Grid"
                for row in rows:
                    cells = table.add_row().cells
                    for cell, text in zip(cells, row): cell.text = str(text)
        doc.save(buffer); buffer.seek(0); Document(buffer)
    elif kind == "xlsx":
        dependency("openpyxl")
        from openpyxl import Workbook, load_workbook
        from openpyxl.workbook.properties import CalcProperties
        doc = Workbook(); doc.remove(doc.active)
        sheets = data["sheets"]
        if not 1 <= len(sheets) <= 20: raise ValueError("Sheet limit")
        for item in sheets:
            sheet = doc.create_sheet(str(item["name"])[:31])
            rows = item["rows"]
            if len(rows) > 10000 or any(len(r) > 100 for r in rows): raise ValueError("Cell limit")
            for row in rows:
                for value in row:
                    if isinstance(value, str) and ("[" in value or re.search(r"(?i)(WEBSERVICE|HYPERLINK|DDE|RTD)\s*\(", value) or "|" in value):
                        raise ValueError("External/active spreadsheet content refused")
                sheet.append(row)
            sheet.freeze_panes = "A2"
        doc.calculation = CalcProperties(fullCalcOnLoad=True)
        doc.save(buffer); buffer.seek(0)
        check = load_workbook(buffer); check.close()
    else:
        raise ValueError("format")
    return buffer.getvalue()


def pdf(p):
    dependency("pypdf")
    from pypdf import PdfReader, PdfWriter
    paths = [Path(v).expanduser().resolve() for v in p.get("files", [])]
    if not paths or len(paths) > 20 or any(f.suffix.lower() != ".pdf" or f.stat().st_size > 30_000_000 for f in paths):
        raise ValueError("1–20 PDFs, each <=30 MB")
    readers = [PdfReader(str(path)) for path in paths]
    if any(r.is_encrypted for r in readers) or sum(len(r.pages) for r in readers) > 1000:
        raise ValueError("Encrypted/oversize PDF")
    if p["action"] == "extract":
        text = "\n".join(page.extract_text() or "" for r in readers for page in r.pages[:100])[:100000]
        return text
    writer = PdfWriter()
    if p["action"] == "merge":
        for r in readers:
            for page in r.pages: writer.add_page(page)
    elif p["action"] == "split":
        if len(readers) != 1: raise ValueError("Split accepts one PDF")
        pages = p.get("pages", [])
        if not pages or any(isinstance(i, bool) or not isinstance(i, int) or not 1 <= i <= len(readers[0].pages) for i in pages):
            raise ValueError("1-based page numbers required")
        for index in pages: writer.add_page(readers[0].pages[index - 1])
    else:
        raise ValueError("action")
    buffer = io.BytesIO(); writer.write(buffer); buffer.seek(0)
    if len(PdfReader(buffer).pages) != len(writer.pages): raise RuntimeError("PDF verification failed")
    return created(buffer.getvalue(), ".pdf", p.get("title", "PDF-JINX"))


def convert(p):
    exe = shutil.which("soffice") or next((str(path) for path in [Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "LibreOffice/program/soffice.exe"] if path.is_file()), None)
    if not exe:
        raise RuntimeError("Conversão requer LibreOffice instalado; alternativa: Exportar PDF no Office / Conversion requires installed LibreOffice; alternative: Export PDF in Office")
    files = p.get("files", [])
    if len(files) != 1: raise ValueError("One Office file required")
    source = Path(files[0]).resolve()
    if source.suffix.lower() not in (".docx", ".pptx", ".xlsx") or not source.is_file(): raise ValueError("Office file required")
    with tempfile.TemporaryDirectory(prefix="jinx-pdf-") as temp:
        profile = (Path(temp) / "profile").as_uri()
        result = subprocess.run([exe, "-env:UserInstallation=" + profile, "--headless", "--convert-to", "pdf", "--outdir", temp, str(source)],
            capture_output=True, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        target = Path(temp) / (source.stem + ".pdf")
        if result.returncode or not target.is_file() or not target.read_bytes().startswith(b"%PDF-"):
            raise RuntimeError("PDF conversion not verified")
        return created(target.read_bytes(), ".pdf", source.stem)
