"""Handler da skill xlsx.

Valida entradas, prepara pasta/nome de saída e devolve o pipeline com
gates (mostrar resultado e perguntar). Não executa a tarefa — o agente
executa com file_processor, openpyxl e pandas conforme o SKILL.md.
"""
from __future__ import annotations

import os
import unicodedata
from pathlib import Path
from typing import Any

from skills.base import BaseSkill, SkillContext, SkillResult

ACTIONS = {"read", "create", "edit", "convert"}


def _slugify(value: str, fallback: str = "planilha") -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    out = []
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-")[:50] or fallback


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
        if action not in ACTIONS:
            return SkillResult(
                status="failed",
                message="Ação inválida. Use action ∈ {read, create, edit, convert}.",
            )
        if action == "create":
            return self._create(params, ctx)

        raw_path = str(params.get("path", "")).strip()
        if not raw_path:
            return SkillResult(
                status="failed",
                message=f"Ação '{action}' exige 'path'. Informe: "
                        "{'action': '" + action + "', 'path': caminho do arquivo}.",
            )
        target = Path(raw_path).expanduser()
        if not target.is_file():
            return SkillResult(
                status="failed",
                message=f"Arquivo não encontrado: {raw_path}. Confirme o caminho "
                        "absoluto (xlsx, xlsm, csv ou tsv) e tente de novo.",
            )

        sheet = str(params.get("sheet", "")).strip()
        sheet_note = f", aba '{sheet}'" if sheet else ""

        if action == "read":
            message = (
                f"Planilha localizada: {target}{sheet_note}. Leia com a tool "
                "nativa file_processor para conferência rápida; para modelo "
                "completo (fórmulas E valores) use openpyxl em DUAS cargas: "
                "default devolve fórmulas, data_only=True devolve valores em "
                "cache — nunca salve a partir da carga data_only (derruba as "
                "fórmulas). .xlsm pede keep_vba=True."
            )
            return SkillResult(
                status="done", message=message,
                data={"path": str(target), "sheet": sheet or None},
            )

        if action == "edit":
            message = (
                f"Edição de {target}{sheet_note} (SKILL.md xlsx): "
                "1) siga as convenções existentes — localize as células de "
                "input designadas e escreva só nelas, sem tocar nas fórmulas "
                "existentes; "
                "2) salve primeiro num arquivo novo, não sobre o original "
                "(Excel aberto = PermissionError no Windows); "
                "3) fórmula referencia célula de input nomeada, com guarda de "
                "divisão por zero e number_format; "
                "4) validação: reabra com openpyxl e confira fórmulas, tipos e "
                "valores conhecidos (recalc via LibreOffice é dependência "
                "externa opcional). "
                "Antes de encerrar, mostre o resultado e pergunte se está correto."
            )
            return SkillResult(
                status="done", message=message,
                data={"path": str(target), "sheet": sheet or None},
            )

        # convert
        out = str(params.get("out", "")).strip()
        if out and Path(out).suffix.lower() in {".xlsx", ".csv", ".tsv"}:
            target_out = Path(out).expanduser()
            target_out.parent.mkdir(parents=True, exist_ok=True)
        elif out:
            folder = Path(out).expanduser()
            folder.mkdir(parents=True, exist_ok=True)
            target_out = folder / (target.stem + ".xlsx")
        else:
            target_out = target.with_suffix(".xlsx")
        _open_folder(target_out.parent)
        message = (
            f"Conversão de {target}{sheet_note} (SKILL.md xlsx). Alvo "
            f"proposto: {target_out}. Use pandas/openpyxl: xlsx→csv com "
            "encoding='utf-8-sig' (Excel abre acento direito); csv→xlsx "
            "recria os tipos. AVISE o que a conversão perde: formatação, "
            "fórmulas viram valores, múltiplas abas exigem escolha, datas em "
            "CSV viram texto. Antes de sobrescrever um arquivo que já existe, "
            "mostre e peça aprovação ao usuário."
        )
        return SkillResult(
            status="done",
            message=message,
            data={"path": str(target), "output_path": str(target_out),
                  "conflicts": [str(target_out)] if target_out.exists() else [],
                  "overwrite_needs_approval": target_out.exists()},
        )

    def _create(self, params: dict[str, Any], ctx: SkillContext) -> SkillResult:
        sheet_plan = str(params.get("sheet_plan", "")).strip()
        if not sheet_plan:
            return SkillResult(
                status="failed",
                message="Para criar uma planilha, monte primeiro o outline e "
                        "informe em 'sheet_plan': colunas, aba(s), fórmulas "
                        "esperadas, formatação e fonte dos dados. Reenvie com "
                        "{'action': 'create', 'sheet_plan': '...' } (e, se "
                        "quiser, 'out').",
            )
        out = str(params.get("out", "")).strip()
        seed = sheet_plan.splitlines()[0] if sheet_plan else ""
        if out and Path(out).suffix.lower() in {".xlsx", ".xlsm"}:
            folder = Path(out).expanduser().parent
            target = Path(out).expanduser()
        elif out:
            folder = Path(out).expanduser()
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / (_slugify(seed) + ".xlsx")
        else:
            folder = _base_dir(ctx)
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / (_slugify(seed) + ".xlsx")
        _open_folder(folder)
        message = (
            f"Pasta de saída pronta: {folder}. Alvo da planilha: {target}. "
            "Crie com openpyxl (SKILL.md xlsx): "
            "1) dados com header em ws.append — sempre; "
            "2) todo número de input em célula própria e rotulada; fórmulas "
            "referenciam essas células (nunca valor inline), com a mesma "
            "fórmula por período/coluna e guarda de divisão por zero; "
            "3) number_format em cada célula de fórmula; "
            "4) largura de coluna manual (autofit é manual); "
            "5) funções era Excel-2007 (SUMIFS/INDEX/MATCH/IFERROR) — nunca "
            "XLOOKUP/SORT/FILTER; "
            "6) workbook para preencher ganha legenda de quais células editar "
            "+ linha de exemplo. "
            "Valide reabrindo com openpyxl e confira fórmulas/tipos, mostre o "
            "resultado ao usuário e pergunte antes de assumir que está pronto."
        )
        return SkillResult(
            status="done",
            message=message,
            data={"folder": str(folder), "output_path": str(target)},
        )


# Alias para runtimes que esperam a classe exposta como "Skill".
Skill = Handler
