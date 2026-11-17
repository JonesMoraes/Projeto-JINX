"""Create, merge, split, cover, OCR, and inspect PDFs without overwriting inputs."""
from __future__ import annotations

import hashlib
import io
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from xml.sax.saxutils import escape

from core import outcome, undo

_MAX_BYTES = 250 * 1024 * 1024
_MAX_PAGES = 2000


def _inputs(raw) -> list[Path]:
    if not isinstance(raw, list) or not raw or len(raw) > 100:
        raise ValueError("files must contain between 1 and 100 PDF paths")
    paths = []
    for value in raw:
        path = Path(str(value)).expanduser()
        if path.is_symlink() or not path.is_file() or path.suffix.lower() != ".pdf":
            raise ValueError(f"not a regular PDF file: {value}")
        path = path.resolve(strict=True)
        if path.stat().st_size > _MAX_BYTES:
            raise ValueError(f"PDF exceeds 250 MiB: {path.name}")
        paths.append(path)
    return paths


def _destination(raw: str, default: str) -> Path:
    path = Path(raw).expanduser().absolute() if raw else Path(default).expanduser().absolute()
    if path.exists():
        raise FileExistsError(f"output exists; choose a new path: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _write_verified(writer, target: Path) -> None:
    fd, raw = tempfile.mkstemp(prefix=f".{target.stem}.", suffix=".pdf", dir=target.parent)
    temp = Path(raw)
    try:
        with open(fd, "wb", closefd=True) as stream:
            writer.write(stream)
            stream.flush()
        data = temp.read_bytes()
        if not data.startswith(b"%PDF-"):
            raise RuntimeError("PDF signature verification failed")
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data), strict=True)
        if not reader.pages or len(reader.pages) > _MAX_PAGES:
            raise RuntimeError("PDF page-count verification failed")
        reader.close()
        temp.replace(target)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        def remove_created() -> str:
            if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                return outcome.failed("pdf_undo", "PDF changed after creation; left untouched.")
            target.unlink()
            return outcome.done("pdf_undo", removed=True)
        undo.push_undo("PDF output: " + target.name, remove_created)
    finally:
        temp.unlink(missing_ok=True)


def _create_text(title: str, content: str, target: Path) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    styles = getSampleStyleSheet()
    story = [Paragraph(escape(title[:200]), styles["Title"]), Spacer(1, 18)]
    for block in content.split("\n")[:5000]:
        story.append(Paragraph(escape(block[:4000]) or "&nbsp;", styles["BodyText"]))
        story.append(Spacer(1, 6))
    buffer = io.BytesIO()
    SimpleDocTemplate(buffer, pagesize=A4, title=title[:200]).build(story)
    from pypdf import PdfReader, PdfWriter
    writer = PdfWriter()
    writer.append(PdfReader(buffer, strict=True))
    _write_verified(writer, target)


def _cover_pdf(title: str, subtitle: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    page.setFont("Helvetica-Bold", 26)
    page.drawCentredString(width / 2, height * 0.66, title[:100])
    if subtitle:
        page.setFont("Helvetica", 14)
        page.drawCentredString(width / 2, height * 0.59, subtitle[:200])
    page.save()
    return buffer.getvalue()


def pdf_forge(parameters: dict, **_context) -> str:
    p = parameters or {}
    action = str(p.get("action", "")).lower()
    try:
        from pypdf import PdfReader, PdfWriter
        if action == "create":
            target = _destination(str(p.get("output_path", "")),
                                  str(Path.home() / "Documents" / f"jinx-{uuid.uuid4().hex[:8]}.pdf"))
            _create_text(str(p.get("title") or "JINX"), str(p.get("text") or ""), target)
            return outcome.done("pdf_create", path=str(target), pages=PdfReader(target).get_num_pages(), verified=True)
        if action == "ocr":
            files = _inputs([p.get("file_path", "")])
            executable = shutil.which("ocrmypdf")
            if not executable:
                return outcome.failed("pdf_ocr", "ocrmypdf command is not installed; OCR is unavailable.")
            target = _destination(str(p.get("output_path", "")),
                                  str(files[0].with_name(files[0].stem + "-ocr.pdf")))
            completed = subprocess.run([executable, "--skip-text", str(files[0]), str(target)],
                                       capture_output=True, text=True, encoding="utf-8",
                                       errors="replace", timeout=3600)
            if completed.returncode != 0:
                target.unlink(missing_ok=True)
                return outcome.failed("pdf_ocr", (completed.stderr or "OCR failed")[-2000:])
            reader = PdfReader(target, strict=True)
            pages = len(reader.pages)
            if not pages or pages > _MAX_PAGES:
                target.unlink(missing_ok=True)
                return outcome.failed("pdf_ocr", "OCR output failed page verification.")
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            undo.push_undo("OCR PDF: " + target.name, lambda: _delete_if_hash(target, digest))
            return outcome.done("pdf_ocr", path=str(target), pages=pages, verified=True)
        if action == "extract_text":
            files = _inputs([p.get("file_path", "")])
            reader = PdfReader(files[0], strict=True)
            if len(reader.pages) > _MAX_PAGES:
                raise ValueError("PDF exceeds the 2,000-page processing limit")
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
            return outcome.done("pdf_extract", text=outcome.untrusted("local-pdf", text[:30_000]),
                                pages=len(reader.pages))
        files = _inputs(p.get("files", [p.get("file_path", "")]))
        if action == "merge":
            writer = PdfWriter()
            total = 0
            for path in files:
                reader = PdfReader(path, strict=True)
                total += len(reader.pages)
                if total > _MAX_PAGES:
                    raise ValueError("combined PDF exceeds 2,000 pages")
                writer.append(reader)
            target = _destination(str(p.get("output_path", "")),
                                  str(files[0].with_name(files[0].stem + "-merged.pdf")))
            _write_verified(writer, target)
            return outcome.done("pdf_merge", path=str(target), pages=total, verified=True)
        if action == "split":
            if len(files) != 1:
                raise ValueError("split requires one PDF")
            reader = PdfReader(files[0], strict=True)
            if len(reader.pages) > _MAX_PAGES:
                raise ValueError("PDF exceeds the 2,000-page split limit")
            folder = _destination(str(p.get("output_dir", "")),
                                  str(files[0].with_name(files[0].stem + "-pages")))
            folder.mkdir(parents=True)
            created = []
            for index, page in enumerate(reader.pages, 1):
                writer = PdfWriter()
                writer.add_page(page)
                target = folder / f"page-{index:04d}.pdf"
                _write_verified(writer, target)
                created.append(str(target))
            return outcome.done("pdf_split", directory=str(folder),
                                files=outcome.untrusted("pdf-output-list", "; ".join(created)),
                                pages=len(created), verified=len(created) == len(reader.pages))
        if action == "cover":
            if len(files) != 1:
                raise ValueError("cover requires one source PDF")
            reader = PdfReader(files[0], strict=True)
            writer = PdfWriter()
            writer.append(PdfReader(io.BytesIO(_cover_pdf(str(p.get("title") or "Document"),
                                                          str(p.get("subtitle") or ""))), strict=True))
            writer.append(reader)
            target = _destination(str(p.get("output_path", "")),
                                  str(files[0].with_name(files[0].stem + "-cover.pdf")))
            _write_verified(writer, target)
            return outcome.done("pdf_cover", path=str(target), pages=len(reader.pages) + 1, verified=True)
        return outcome.failed("pdf_forge", "Unsupported action.", action=action)
    except Exception as exc:
        return outcome.failed("pdf_forge", str(exc))


def _delete_if_hash(path: Path, digest: str) -> str:
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        return outcome.failed("pdf_undo", "PDF changed after creation; left untouched.")
    path.unlink()
    return outcome.done("pdf_undo", removed=True)


TOOL = {
    "name": "pdf_forge",
    "description": "Create searchable text PDFs, merge or split PDFs, add a generated cover, extract text, and OCR with optional OCRmyPDF. Inputs are preserved and outputs are verified.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["create", "merge", "split", "cover", "ocr", "extract_text"]},
            "files": {"type": "ARRAY", "items": {"type": "STRING"}},
            "file_path": {"type": "STRING"}, "output_path": {"type": "STRING"},
            "output_dir": {"type": "STRING"}, "title": {"type": "STRING"},
            "subtitle": {"type": "STRING"}, "text": {"type": "STRING"},
        },
        "required": ["action"],
    },
    "handler": pdf_forge,
    "behavior": "NON_BLOCKING",
    "scheduling": "WHEN_IDLE",
    "tier": "extra",
    "brief": "Create, merge, split, cover, OCR and extract PDFs.",
}
