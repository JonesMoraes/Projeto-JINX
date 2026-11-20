"""Handler da skill docx.

Valida entradas, prepara pasta/nome de saída e devolve o passo a passo
para o agente executar a tarefa com as tools nativas e python-docx —
nunca executa a tarefa em si.
"""
from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from typing import Any

from skills.base import BaseSkill, SkillContext, SkillResult


def _slugify(value: str, fallback: str = "documento") -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    out = []
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    slug = "".join(out).strip("-")
    return slug[:50] or fallback


def _unique_path(folder: Path, name: str) -> Path:
    target = folder / name
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix or ".docx"
    for i in range(2, 100):
        candidate = folder / f"{stem}-{i}{suffix}"
        if not candidate.exists():
            return candidate
    return target


def _base_dir(ctx: SkillContext | None) -> Path:
    meta = (ctx.metadata if ctx is not None else None) or {}
    home = meta.get("jinx_home") or meta.get("cwd")
    return Path(str(home)) if home else Path.cwd()


def _open_folder(folder: Path) -> None:
    """Abre a pasta no Explorer (Windows) sem levantar erro se falhar."""
    try:
        if os.name == "nt":
            os.startfile(str(folder))  # noqa: S606
    except Exception:  # noqa: BLE001 — abrir o Explorer é best-effort
        pass


_GATES = (
    "Antes de encerrar: mostre o documento gerado ao usuário e pergunte se "
    "está correto — não assuma que está pronto sem essa conferência."
)


class Handler(BaseSkill):
    async def run(self, params: dict[str, Any], ctx: SkillContext) -> SkillResult:
        action = str(params.get("action", "")).strip().lower()
        if action not in {"read", "create", "edit", "ooxml"}:
            return SkillResult(
                status="failed",
                message="Ação inválida. Use action ∈ {read, create, edit, ooxml}.",
            )

        # create não exige path: monta nome seguro e pasta de saída.
        if action == "create":
            return self._create(params, ctx)

        raw_path = str(params.get("path", "")).strip()
        if not raw_path:
            return SkillResult(
                status="failed",
                message=f"Ação '{action}' exige 'path'. Informe: "
                        "{'action': '" + action + "', 'path': caminho do .docx}.",
            )
        target = Path(raw_path).expanduser()
        if not target.is_file():
            return SkillResult(
                status="failed",
                message=f"Arquivo não encontrado: {raw_path}. Confirme o caminho "
                        "absoluto do .docx e tente de novo.",
            )

        if action == "read":
            message = (
                f"Documento localizado: {target}. Leia o conteúdo com a tool "
                "nativa file_processor (lê docx) para o texto; se precisar de "
                "estrutura (estilos, tabelas, seções), use python-docx "
                "document.paragraphs/tables/sections. Para .doc legado, avise "
                "que a conversão depende de LibreOffice — dependência externa "
                "opcional que pode não estar instalada."
            )
            return SkillResult(
                status="done", message=message, data={"path": str(target)}
            )

        if action == "edit":
            message = (
                f"Edição leve em {target} via python-docx (SKILL.md): "
                "1) percorra parágrafos E células de tabela; "
                "2) troque texto por run — atribua em run.text, JAMAIS em "
                "paragraph.text/text_frame.text (destrói a formatação); "
                "3) lembre que o Word fragmenta frases em vários runs — a "
                "frase visível raramente existe contígua num run só; "
                "4) se a mudança exigir XML que python-docx não expõe, use "
                "action='ooxml'. "
                f"{_GATES}"
            )
            return SkillResult(
                status="done", message=message, data={"path": str(target)}
            )

        # ooxml
        message = (
            f"Edição OOXML profunda em {target} (SKILL.md): "
            "1) descompacte com zipfile.extractall (nunca ferramenta que "
            "restaura symlinks — arquivo externo não é confiável); "
            "2) edite unpacked/word/document.xml in place, sem reformatar o XML; "
            "3) rezipe TODOS os arquivos preservando [Content_Types].xml e as "
            "pastas _rels/, para um novo .docx; "
            "4) comentários exigem seis arquivos entreligados e os marcadores "
            "commentRangeStart/End + commentReference no document.xml — sem os "
            "marcadores o comentário fica invisível; evite criar comentários "
            "via OOXML cru. "
            f"{_GATES}"
        )
        return SkillResult(
            status="done", message=message, data={"path": str(target)}
        )

    def _create(self, params: dict[str, Any], ctx: SkillContext) -> SkillResult:
        content = str(params.get("content", "")).strip()
        raw_out = str(params.get("out", "")).strip()

        seed = content or "documento"
        name = _slugify(re.split(r"[\n.;:]", seed, maxsplit=1)[0])

        folder = Path(raw_out).expanduser() if raw_out else _base_dir(ctx)
        folder.mkdir(parents=True, exist_ok=True)
        target = _unique_path(folder, name + ".docx")
        _open_folder(folder)

        message = (
            f"Pasta de saída pronta: {folder}. Nome seguro escolhido: "
            f"{target.name}. Construa o documento com python-docx (SKILL.md): "
            "1) estilos/títulos built-in (Heading 1..3) para o sumário "
            "funcionar; "
            "2) nunca use \\n — um add_paragraph/add_heading por item; "
            "3) listas com os estilos 'List Bullet'/'List Number', nunca '•' "
            "literal; "
            "4) tabelas com autofit=False e largura em cada célula; "
            "5) TOC e número de página no rodapé via campo w:fldSimple "
            "(TOC \\o \"1-3\" \\h \\z \\u / PAGE) — o Word popula ao atualizar "
            "campos, avise o usuário; "
            "6) imagens sempre com width=Inches(...) para não estourar a página. "
            f"Salvar em: {target}. {_GATES}"
        )
        return SkillResult(
            status="done",
            message=message,
            data={"folder": str(folder), "output_path": str(target)},
        )


# Alias para runtimes que esperam a classe exposta como "Skill".
Skill = Handler
