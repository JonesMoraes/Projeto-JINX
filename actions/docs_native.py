"""Read native Office documents and make versioned, verified XLSX range edits."""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path

from core import outcome, undo

_MAX_FILE_BYTES = 100 * 1024 * 1024


def _source(raw: str) -> Path:
    path = Path(str(raw or "")).expanduser()
    if not path.is_file() or path.is_symlink():
        raise ValueError("file_path must point to an existing regular file")
    if path.stat().st_size > _MAX_FILE_BYTES:
        raise ValueError("document exceeds 100 MiB")
    return path.resolve(strict=True)


def _read_document(path: Path, sheet: str = "", cell_range: str = "") -> str:
    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        from openpyxl import load_workbook
        workbook = load_workbook(path, read_only=True, data_only=False)
        try:
            worksheet = workbook[sheet] if sheet else workbook.active
            cells = worksheet[cell_range] if cell_range else worksheet.iter_rows()
            rows = []
            for row in cells:
                if not isinstance(row, tuple):
                    row = (row,)
                rows.append("\t".join("" if cell.value is None else str(cell.value)
                                      for cell in row))
                if len(rows) >= 200:
                    rows.append("[truncated at 200 rows]")
                    break
            return "\n".join(rows)
        finally:
            workbook.close()
    if suffix == ".docx":
        from docx import Document
        doc = Document(path)
        rows = [paragraph.text for paragraph in doc.paragraphs if paragraph.text.strip()]
        for table in doc.tables[:20]:
            rows.extend("\t".join(cell.text for cell in row.cells) for row in table.rows[:100])
        return "\n".join(rows[:500])
    if suffix == ".pptx":
        from pptx import Presentation
        deck = Presentation(path)
        rows = []
        for index, slide in enumerate(deck.slides, start=1):
            text = " | ".join(shape.text for shape in slide.shapes if getattr(shape, "has_text_frame", False)
                              and shape.text.strip())
            rows.append(f"Slide {index}: {text}")
        return "\n".join(rows[:200])
    raise ValueError("read supports .xlsx, .docx, and .pptx")


def _new_destination(source: Path, requested: str = "") -> Path:
    if requested:
        target = Path(requested).expanduser().absolute()
        if target.resolve(strict=False) == source:
            raise ValueError("output must not overwrite the source document")
        if target.exists():
            raise FileExistsError("output already exists; choose a new output_path")
        return target
    base = source.with_name(source.stem + "-jinx-edited")
    target = base.with_suffix(source.suffix)
    index = 1
    while target.exists():
        target = base.with_name(base.name + f"-v{index}").with_suffix(source.suffix)
        index += 1
    return target


def _write_cells(source: Path, sheet: str, cell_range: str, values,
                 output_path: str = "") -> str:
    if source.suffix.lower() != ".xlsx":
        raise ValueError("write_cells currently supports .xlsx only")
    if not sheet or not cell_range:
        raise ValueError("sheet and cell_range are required")
    if not isinstance(values, list) or not values or any(not isinstance(row, list) for row in values):
        raise ValueError("values must be a non-empty two-dimensional array")
    from openpyxl import load_workbook
    from openpyxl.utils.cell import range_boundaries

    min_col, min_row, max_col, max_row = range_boundaries(cell_range)
    if len(values) != max_row - min_row + 1 or any(
            len(row) != max_col - min_col + 1 for row in values):
        raise ValueError("values dimensions must exactly match cell_range")
    target = _new_destination(source, output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_temp = tempfile.mkstemp(prefix=f".{target.stem}.", suffix=".xlsx",
                                    dir=target.parent)
    os.close(fd)
    temp = Path(raw_temp)
    try:
        shutil.copy2(source, temp)
        workbook = load_workbook(temp)
        try:
            if sheet not in workbook.sheetnames:
                raise ValueError(f"worksheet {sheet!r} does not exist")
            worksheet = workbook[sheet]
            for row_index, row in enumerate(values, start=min_row):
                for col_index, value in enumerate(row, start=min_col):
                    worksheet.cell(row_index, col_index).value = value
            workbook.save(temp)
        finally:
            workbook.close()
        # Reopen the saved artifact and verify every requested cell.
        verify = load_workbook(temp, read_only=True, data_only=False)
        try:
            check = verify[sheet]
            for row_index, row in enumerate(values, start=min_row):
                for col_index, value in enumerate(row, start=min_col):
                    if check.cell(row_index, col_index).value != value:
                        raise RuntimeError("saved cell values did not verify")
        finally:
            verify.close()
        os.replace(temp, target)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()

        def remove_created() -> str:
            if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                return outcome.failed("docs_native_undo", "Output changed; left untouched.")
            target.unlink()
            return outcome.done("docs_native_undo", removed=True)

        undo.push_undo("Office output: " + target.name, remove_created)
        return str(target)
    finally:
        temp.unlink(missing_ok=True)


def docs_native(parameters: dict, **_context) -> str:
    p = parameters or {}
    try:
        path = _source(p.get("file_path", ""))
        action = str(p.get("action", "read")).lower()
        if action == "read":
            text = _read_document(path, str(p.get("sheet", "")),
                                  str(p.get("cell_range", "")))
            return outcome.done("docs_native_read", file=str(path),
                                text=outcome.untrusted("local-document", text[:30_000]))
        if action == "write_cells":
            target = _write_cells(path, str(p.get("sheet", "")),
                                  str(p.get("cell_range", "")), p.get("values"),
                                  str(p.get("output_path", "")))
            return outcome.done("docs_native_write", source=str(path), output=target,
                                verified=True, source_preserved=True)
        return outcome.failed("docs_native", "Unsupported action.", action=action)
    except Exception as exc:
        return outcome.failed("docs_native", str(exc))


TOOL = {
    "name": "docs_native",
    "description": "Read XLSX/DOCX/PPTX files and edit an XLSX cell range in a new verified copy, preserving the original workbook.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["read", "write_cells"]},
            "file_path": {"type": "STRING"},
            "sheet": {"type": "STRING"},
            "cell_range": {"type": "STRING"},
            "values": {"type": "ARRAY", "items": {"type": "ARRAY",
                      "items": {"type": "STRING"}}},
            "output_path": {"type": "STRING"},
        },
        "required": ["action", "file_path"],
    },
    "handler": docs_native,
    "tier": "core",
    "brief": "Read Office documents; verify XLSX range edits into a copy.",
}
