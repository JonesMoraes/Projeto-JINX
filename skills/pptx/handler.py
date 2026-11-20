"""Handler da skill pptx.

Valida entradas e devolve o pipeline com gates (criar → QA visual →
revisão final). Não executa a tarefa — o agente executa com python-pptx,
file_processor e edição OOXML conforme o SKILL.md.
"""
from __future__ import annotations

import os
import unicodedata
from pathlib import Path
from typing import Any

from skills.base import BaseSkill, SkillContext, SkillResult


def _slugify(value: str, fallback: str = "deck") -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    out = []
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-")[:50] or fallback


def _unique_path(folder: Path, name: str) -> Path:
    target = folder / name
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix or ".pptx"
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
    try:
        if os.name == "nt":
            os.startfile(str(folder))  # noqa: S606 — best-effort
    except Exception:  # noqa: BLE001
        pass


class Handler(BaseSkill):
    async def run(self, params: dict[str, Any], ctx: SkillContext) -> SkillResult:
        action = str(params.get("action", "")).strip().lower()
        if action not in {"read", "create", "edit"}:
            return SkillResult(
                status="failed",
                message="Ação inválida. Use action ∈ {read, create, edit}.",
            )

        # read / edit: path obrigatório e existente.
        if action in {"read", "edit"}:
            raw_path = str(params.get("path", "")).strip()
            if not raw_path:
                return SkillResult(
                    status="failed",
                    message=f"Ação '{action}' exige 'path'. Informe: "
                            "{'action': '" + action + "', 'path': caminho do .pptx}.",
                )
            target = Path(raw_path).expanduser()
            if not target.is_file():
                return SkillResult(
                    status="failed",
                    message=f"Arquivo não encontrado: {raw_path}. Confirme o "
                            "caminho absoluto do .pptx e tente de novo.",
                )
            if action == "read":
                message = (
                    f"Apresentação localizada: {target}. Leia com a tool "
                    "nativa file_processor (lê pptx slide a slide); para "
                    "detalhe (tabelas, notas, posições), use python-pptx "
                    "iterando prs.slides → slide.shapes. Para .potx, o "
                    "caminho de leitura é o mesmo."
                )
                return SkillResult(
                    status="done", message=message, data={"path": str(target)}
                )

            message = (
                f"Edição OOXML de {target} (SKILL.md pptx): "
                "1) descompacte com zipfile.extractall — arquivo externo é "
                "não confiável; "
                "2) ESTRUTURA antes do conteúdo: adicionar/reordenar/excluir "
                "slides pelo <p:sldIdLst> em ppt/presentation.xml, "
                "registrando rels em [Content_Types].xml e "
                "ppt/_rels/presentation.xml.rels; "
                "3) edite textos em ppt/slides/slideN.xml in place, sem "
                "reformatar o XML; "
                "4) removeu shape animado? apague também o <p:timing> do "
                "slide, senão o PowerPoint oferece reparar o arquivo; "
                "5) rezipe TODOS os arquivos preservando [Content_Types].xml "
                "e _rels/. "
                "Siga pro QA visual obrigatório (SKILL.md) e mostre o deck "
                "ao usuário antes de assumir que está pronto."
            )
            return SkillResult(
                status="done", message=message, data={"path": str(target)}
            )

        # create: exige deck_plan.
        deck_plan = str(params.get("deck_plan", "")).strip()
        if not deck_plan:
            return SkillResult(
                status="failed",
                message="Para criar um deck, monte primeiro o outline e "
                        "informe em 'deck_plan': mensagem por slide, seções, "
                        "dados/gráficos que entram, público e tom. Reenvie "
                        "com {'action': 'create', 'deck_plan': '...'} e, se "
                        "quiser, 'out' (pasta de saída).",
            )

        raw_out = str(params.get("out", "")).strip()
        seed = deck_plan.splitlines()[0] if deck_plan else ""
        folder = Path(raw_out).expanduser() if raw_out else _base_dir(ctx)
        folder.mkdir(parents=True, exist_ok=True)
        target = _unique_path(folder, _slugify(seed) + ".pptx")
        _open_folder(folder)

        message = (
            f"Pasta de saída pronta: {folder}. Alvo do deck: {target}. "
            "Pipeline com gates — não pule etapas: "
            "1) CRIAR com python-pptx (SKILL.md pptx): defina "
            "prs.slide_width=Inches(13.333) e slide_height=Inches(7.5) "
            "ANTES de adicionar slides; cores hex sem '#' "
            "(RGBColor.from_string); confira que nenhum shape passa dos "
            "limites do slide (não clampam); bullets herdados de "
            "placeholder, nunca '•' literal; notas via notes_slide. "
            "→ Gate: mostre o deck criado ao usuário. "
            "2) QA visual obrigatório (SKILL.md pptx): overflow de texto é "
            "o defeito nº 1 — cheque cortes, sobreposições, gaps desiguais, "
            "contraste e placeholder esquecido. LibreOffice/pdftoppm são "
            "dependências externas opcionais; sem elas, abra no PowerPoint "
            "(start) e revise com o usuário. → Gate. "
            "3) REVISÃO FINAL: remini o conteúdo (typos, ordem, slides de "
            "mesmo tipo consistentes) e reavalie; só declare pronto com "
            "aprovação do usuário."
        )
        return SkillResult(
            status="done",
            message=message,
            data={
                "folder": str(folder),
                "output_path": str(target),
                "pipeline": [
                    {"step": 1, "task": "criar com python-pptx (widescreen 13,33x7,5)"},
                    {"step": 2, "task": "QA visual (overflow, sobreposição, contraste)", "gate": True},
                    {"step": 3, "task": "revisão final", "gate": True},
                ],
            },
        )


# Alias para runtimes que esperam a classe exposta como "Skill".
Skill = Handler
