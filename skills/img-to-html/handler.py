"""Handler da skill img-to-html.

Prepara a pasta design-systems/<slug>/ (cópia da referência) e devolve o
pipeline em camadas com gates de aprovação, para o agente executar passo a passo.
"""
from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from skills.base import BaseSkill, SkillContext, SkillResult


def _slugify(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    out = []
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    slug = "".join(out).strip("-")
    return slug[:40] or "mock"


def _extension(source: str, data: bytes) -> str:
    suffix = Path(urlparse(source).path).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
        return ".jpeg" if suffix == ".jpg" else suffix
    data_head = data[:16]
    if data_head.startswith(b"\x89PNG"):
        return ".png"
    if data_head.startswith(b"GIF"):
        return ".gif"
    if data_head.startswith(b"\xff\xd8"):
        return ".jpeg"
    if data_head.startswith(b"RIFF"):
        return ".webp"
    return ".png"


def _read_image(source: str) -> tuple[bytes, str]:
    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"}:
        req = Request(source, headers={"User-Agent": "JINX img-to-html"})
        with urlopen(req, timeout=60) as resp:
            data = resp.read()
        return data, source
    path = Path(source).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"imagem de referência não encontrada: {source}")
    return path.read_bytes(), str(path)


class Handler(BaseSkill):
    async def run(self, params: dict[str, Any], ctx: SkillContext) -> SkillResult:
        image = str(params.get("image", "")).strip()
        if not image:
            return SkillResult(
                status="failed",
                message="Informe a imagem de referência: {'image': caminho ou URL}.",
            )
        try:
            data, source_path = _read_image(image)
        except Exception as exc:  # noqa: BLE001
            return SkillResult(status="failed", message=str(exc))

        slug = _slugify(str(params.get("slug", "")) or Path(urlparse(source_path).path).stem)
        ext = _extension(source_path, data)

        base = Path((ctx.metadata or {}).get("cwd") or Path.cwd()) / "design-systems" / slug
        base.mkdir(parents=True, exist_ok=True)
        (base / "assets" / "crops").mkdir(parents=True, exist_ok=True)
        reference = base / f"reference{ext}"
        reference.write_bytes(data)

        return SkillResult(
            status="done",
            message=(
                f"Referência copiada para {reference}. "
                "Siga o pipeline da skill (SKILL.md): "
                "1) wireframe ASCII tipado em wireframe.txt + plano por região → gate; "
                "2) fundo completo → gate; "
                "3) estrutura/componentes + fontes → gate; "
                "4) assets restantes (se houver) → gate; "
                "5) revisão final integrada → gate. "
                "NÃO comece a etapa seguinte sem aprovação explícita do usuário.",
            ),
            data={
                "slug": slug,
                "folder": str(base),
                "reference": str(reference),
                "pipeline": [
                    {"step": 1, "task": "wireframe tipado + plano", "gate": True},
                    {"step": 2, "task": "fundo completo", "gate": True},
                    {"step": 3, "task": "estrutura + fontes", "gate": True},
                    {"step": 4, "task": "assets restantes", "gate": True},
                    {"step": 5, "task": "revisão final", "gate": True},
                ],
            },
        )
