import json
from core import office, outcome


def install(values):
    from core.optional_packages import install as packages
    return packages("office")


PLUGIN_SETTINGS = {"namespace": "office_suite", "title": "DOCUMENTOS / DOCUMENTS", "fields": [
    {"key": "output_dir", "label": "Pasta de saída (vazio: Documentos/JINX) / Output folder", "type": "text"}],
    "action": {"label": "INSTALAR DEPENDÊNCIAS OPCIONAIS / INSTALL OPTIONAL DEPENDENCIES", "run": install}}
PLUGIN = {"name": "office_suite", "description": "Create pptx/docx/xlsx from topic or content JSON (slides:title,bullets,notes,layout; blocks:heading,text,bullets,table; sheets:name,rows with formulas). PDF merge/split selected 1-based pages/extract, convert Office via installed LibreOffice. Created files have undo.",
    "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING", "enum": ["create", "merge", "split", "extract", "convert"]},
    "format": {"type": "STRING", "enum": ["pptx", "docx", "xlsx"]}, "topic": {"type": "STRING"},
    "content": {"type": "STRING", "description": "Optional structured JSON"}, "title": {"type": "STRING"},
    "count": {"type": "INTEGER"}, "files": {"type": "ARRAY", "items": {"type": "STRING"}},
    "pages": {"type": "ARRAY", "items": {"type": "INTEGER"}}}, "required": ["action"]}}


def run(parameters, player=None, session_memory=None):
    try:
        p = parameters or {}
        action = p.get("action")
        if action == "create":
            kind = p.get("format")
            if kind not in ("pptx", "docx", "xlsx"): raise ValueError("format")
            office.dependency({"pptx": "pptx", "docx": "docx", "xlsx": "openpyxl"}[kind])
            data = office.content(p)
            path = office.created(office.generate(kind, data), "." + kind, p.get("title") or data.get("title", "JINX"))
        elif action == "extract":
            text = office.pdf(p)
            if player: player.show_content("PDF / PDF", text)
            return outcome.done("pdf_extract", data=outcome.untrusted("pdf-document", text))
        elif action in ("merge", "split"):
            path = office.pdf(p)
        elif action == "convert":
            path = office.convert(p)
        else: raise ValueError("action")
        if player: player.show_content("Arquivo criado / File created", path)
        return outcome.done("office_suite", path=path, note="Arquivo reaberto/verificado; fórmulas recalculam no aplicativo de planilhas / File reopened/verified; formulas recalculate in spreadsheet app")
    except Exception as exc:
        return outcome.failed("office_suite", str(exc)[:250])
