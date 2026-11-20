"""Handler da skill pdf.

Valida caminhos, detecta colisões de saída e devolve o pipeline com o gate
de aprovação antes de sobrescrever arquivos. Não executa merge/split/etc —
isso é do agente, com pdf_forge/file_processor ou as bibliotecas.
"""
from __future__ import annotations

import os
import unicodedata
from pathlib import Path
from typing import Any

from skills.base import BaseSkill, SkillContext, SkillResult

_MIN_PATHS = {"read": 1, "merge": 2, "split": 1, "edit": 1}


def _slugify(value: str, fallback: str = "pdf") -> str:
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


def _resolve_paths(values: Any) -> list[Path]:
    items = [str(v).strip() for v in (values or []) if str(v).strip()]
    return [Path(v).expanduser() for v in items]


def _open_folder(folder: Path) -> None:
    try:
        if os.name == "nt":
            os.startfile(str(folder))  # noqa: S606
    except Exception:  # noqa: BLE001 — best-effort
        pass


class Handler(BaseSkill):
    async def run(self, params: dict[str, Any], ctx: SkillContext) -> SkillResult:
        action = str(params.get("action", "")).strip().lower()
        if action not in {"read", "merge", "split", "create", "edit"}:
            return SkillResult(
                status="failed",
                message="Ação inválida. Use action ∈ {read, merge, split, create, edit}.",
            )

        if action == "create":
            return self._create(params, ctx)

        paths = _resolve_paths(params.get("paths"))
        if len(paths) < _MIN_PATHS[action]:
            return SkillResult(
                status="failed",
                message=f"Ação '{action}' exige ao menos "
                        f"{_MIN_PATHS[action]} caminho(s) em 'paths': "
                        "{'paths': [caminhos .pdf]}.",
            )
        missing = [str(p) for p in paths if not p.is_file()]
        if missing:
            return SkillResult(
                status="failed",
                message="PDF não encontrado: " + "; ".join(missing) +
                        ". Confirme os caminhos absolutos e tente de novo.",
            )

        out = Path(str(params.get("out", "")).strip()).expanduser() \
            if str(params.get("out", "")).strip() else None

        if action == "read":
            message = (
                f"{len(paths)} PDF(s) validado(s). Leia com a tool nativa "
                "file_processor (texto e tabelas via pdfplumber); para acesso "
                "detalhado, use pdfplumber: page.extract_text() e "
                "page.extract_tables() por página. Tabelas podem virar CSV. "
                "Se o texto vier vazio, é PDF escaneado: o OCR depende de "
                "pdftoppm+pytesseract — dependência externa opcional, avise "
                "o usuário se não houver."
            )
            return SkillResult(
                status="done",
                message=message,
                data={"paths": [str(p) for p in paths]},
            )

        # merge / split / edit: definir saída e colisões.
        out_dir = (out if out and out.suffix == "" else
                   (out.parent if out else paths[0].parent))
        out_dir.mkdir(parents=True, exist_ok=True)

        if action == "merge":
            default_out = out if out and out.suffix else None
            name = default_out.name if default_out else _slugify(
                paths[0].stem + "-juntado") + ".pdf"
            outputs_data = [("merged", out_dir / name)]
            message = (
                f"Pipeline de merge (fonte do texto: SKILL.md pdf): "
                f"1) {' + '.join(str(p) for p in paths)}; "
                f"2) junte as páginas em ordem para {out_dir / name} — "
                "preferindo a tool nativa pdf_forge (merge), ou pypdf "
                "PdfWriter.add_page página a página; "
                "3) escreva num arquivo NOVO, nunca sobre as entradas."
            )
        elif action == "split":
            name_seed = paths[0].stem
            outputs_data = [("paged", out_dir / f"{_slugify(name_seed)}-pagina-{i:02d}.pdf")
                            for i in range(1, 2)]
            message = (
                f"Pipeline de split de {paths[0]} (fonte: SKILL.md pdf): "
                f"1) leia o total de páginas (PdfReader len(reader.pages)); "
                f"2) gere 1 arquivo por página em {out_dir} com nome "
                f"<slug>-pagina-NN.pdf — preferindo a tool nativa pdf_forge "
                "(split), ou pypdf (um PdfWriter por página); "
                "3) opções de páginas específicas via options.pages "
                "('{pages: \"1-5,8\"}'). Escreva sempre em arquivos novos."
            )
        else:  # edit
            outputs_data = [("edited", out_dir / (paths[0].stem + "-editado.pdf"))]
            options = params.get("options") or {}
            message = (
                f"Pipeline de edição de {paths[0]} (fonte: SKILL.md pdf): "
                f"1) opções detectadas: {options or nenhuma_opcao_hint()} — "
                "girar (page.rotate(graus)), marca d'água "
                "(page.merge_page do PDF da marca) e senha "
                "(writer.encrypt(user, owner)) com pypdf; "
                f"2) grave como {out_dir / (paths[0].stem + '-editado.pdf')} — "
                "nunca sobre o original; "
                "3) PDF aberto num visualizador dá PermissionError no "
                "Windows: escreva num nome novo."
            )

        outputs = [p for _, p in outputs_data]
        conflicts = [str(p) for p in outputs if p.exists()]
        _open_folder(out_dir)
        if conflicts:
            message += (
                " ATENÇÃO — gate de sobrescrita: os arquivos " +
                "; ".join(conflicts) +
                " já existem. Mostre esta lista ao usuário e PEÇA APROVAÇÃO "
                "EXPLÍCITA antes de sobrescrever; sem aprovação, use nomes novos."
            )
        else:
            message += (" Confira as saídas antes de encerrar: mostre ao "
                        "usuário o resultado e pergunte se está correto.")
        return SkillResult(
            status="done",
            message=message,
            data={
                "paths": [str(p) for p in paths],
                "outputs": [str(p) for p in outputs],
                "conflicts": conflicts,
                "overwrite_needs_approval": bool(conflicts),
            },
        )

    def _create(self, params: dict[str, Any], ctx: SkillContext) -> SkillResult:
        options = params.get("options") or {}
        out = str(params.get("out", "")).strip()
        title = str(options.get("title", "")).strip() or "relatorio"
        folder = (Path(out).expanduser().parent if out and Path(out).suffix
                  else Path(out).expanduser() if out else _base_dir(ctx))
        folder.mkdir(parents=True, exist_ok=True)
        name = Path(out).name if out and Path(out).suffix else _slugify(title) + ".pdf"
        target = folder / name
        _open_folder(folder)
        message = (
            f"Criação de PDF (SKILL.md pdf). Alvo: {target}. "
            "1) Se a tarefa for juntar/montar páginas, prefira a tool nativa "
            "pdf_forge — ela já cria PDF com capa. "
            "2) Para conteúdo novo, use reportlab: SimpleDocTemplate + "
            "Paragraph/Spacer/PageBreak para texto fluido, Canvas para "
            "posicionamento exato; "
            "3) JAMAIS use caracteres Unicode de sub/sobrescrito — viram "
            "quadradinho preto; use <sub>/<super> na marcação do Paragraph; "
            "4) escreva no arquivo novo e confira abrindo o len(reader.pages). "
            "Antes de sobrescrever um arquivo existente, mostre e peça "
            "aprovação ao usuário."
        )
        return SkillResult(
            status="done",
            message=message,
            data={"folder": str(folder), "output_path": str(target),
                  "conflicts": [str(target)] if target.exists() else [],
                  "overwrite_needs_approval": target.exists()},
        )


def nenhuma_opcao_hint() -> str:
    return "nenhuma — pergunte se quer girar, marca d'água ou senha"


# Alias para runtimes que esperam a classe exposta como "Skill".
Skill = Handler
