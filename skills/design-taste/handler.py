"""Handler for the design-taste skill (anti-slop frontend).

Lean and deterministic: validates the brief, optionally creates the output
folder (pathlib, no subprocess), and returns a workflow message with explicit
approval gates. All design intelligence lives in SKILL.md.
"""
from __future__ import annotations

from pathlib import Path

from skills.base import BaseSkill, SkillContext, SkillResult

_CHECKLIST = (
    "primeira tela diz o que vende e para quem, com um fato concreto",
    "uma secao por tela (1440x900); sem h2 da proxima secao espiando",
    "bordas laterais alinhadas; sem scroll horizontal",
    "todo visual renderiza em 1440/1024/768/390 (capturar com "
    "actions/browser_control e screen_processor)",
    "sem legenda sob imagem; creditos numa linha so de rodape",
    "hover discretos: lift 2px, zoom 1.02-1.03, sublinhado que desenha; "
    "hero entra uma vez (data-enter)",
    "fotos reais onde couber; stand-in sempre declarado no relatorio",
    "icones de produto em cor cheia (icones reais, nunca desenho parecido)",
    "contatos verificados e mascarados (rua e bairro, .example, data-assumed)",
    "teclado/a11y completo: alt, labels visiveis, headings em ordem, anel de foco",
    "um sistema: um par de botoes, um estilo de card, uma escala de radius/titulos",
    "performance manual: peso de imagem, CLS reservado, animacao so em "
    "transform/opacity, <= 4 contextos WebGL (0 fora de pagina tecnica)",
)

_NEVER = (
    "fade-in ao rolar em card/secao; parallax em texto; scroll-jacking",
    "foto de banco passando como produto do cliente; pagina de produto sem produto",
    "logo desenhado parecido com um real; review, quote ou numero inventado",
    "violeta ou lavanda na paleta propria (acento, fundo, gradiente ou tint)",
    "copiar codigo, copy ou efeito-assinatura de um site de referencia",
)


def _prepare_output(target: str) -> tuple[Path | None, str | None]:
    """Create the output folder if given; return (path, error)."""
    raw = target.strip()
    if not raw:
        return None, None
    try:
        path = Path(raw).expanduser()
        path = path if path.is_absolute() else Path.cwd() / path
        path = path.resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path, None
    except OSError as exc:
        return None, "Nao consegui criar a pasta de saida {!r}: {}".format(raw, exc)


class Handler(BaseSkill):
    async def run(self, params: dict, ctx: SkillContext) -> SkillResult:
        brief = str(params.get("brief", "")).strip()
        if not brief:
            return SkillResult("failed", "O parametro 'brief' e obrigatorio.")

        stack = str(params.get("stack", "")).strip().lower()
        out_path, out_err = _prepare_output(str(params.get("target", "")))
        if out_err:
            return SkillResult("failed", out_err)

        data = {
            "brief": brief,
            "stack": stack or None,
            "output_dir": str(out_path) if out_path else None,
            "checklist": list(_CHECKLIST),
            "never": list(_NEVER),
            "layers": ["copy", "visual-system", "sections", "browser-check"],
        }

        stack_line = stack if stack else (
            "DETETE a stack do projeto (package.json etc.) ou pergunte; nunca assuma")
        out_line = "Plano e checklist serao gravados em: {}.".format(out_path) \
            if out_path else "Nenhuma pasta de saida informada; registre o plano em memoria."

        message = (
            "Skill design-taste iniciada. {out_line}\n"
            "Stack: {stack_line}.\n"
            "\n"
            "FLUXO EM 4 PASSOS, com gate de aprovacao entre cada um:\n"
            "1. COPY UNICA E VOZ PROPRIA: escreva toda a copy primeiro — h1 nomeia "
            "a categoria e o comprador, um fato concreto na primeira tela, "
            "substantivo nos titulos, botoes verbo + objeto. Nada inventado exceto "
            "nome de marca novo e fatos assumidos marcados. Mostre a copy e "
            "AGUARDE APROVACAO EXPLICITA antes da etapa seguinte.\n"
            "2. SISTEMA VISUAL: defina cor, tipografia e espacamento como um unico "
            "par de botoes, um estilo de card, uma escala de radius e de titulos. "
            "Proibido violeta/lavanda na paleta propria. Mostre o sistema e "
            "AGUARDE APROVACAO antes de escrever codigo.\n"
            "3. SECAO POR SECAO: cada secao mede 1-2 telas em 1440x900, h2 "
            "primeiro, bordas alinhadas, uma secao por tela na primeira dobra; "
            "apresente cada secao e AGUARDE APROVACAO antes da seguinte.\n"
            "4. CHECAGEM FINAL: verifique em um navegador real nas larguras 1440, "
            "1024, 768 e 390 (o JINX tem actions/browser_control e "
            "screen_processor para capturar telas), leia cada captura contra a "
            "checklist e o checklist manual de performance (peso de imagem, CLS, "
            "no-jank), e entregue o relatorio declarando stand-ins e fatos "
            "assumidos.\n"
            "\n"
            "NUNCA: fade-in ao rolar em cada card, parallax em texto, "
            "scroll-jacking, foto de banco passando como produto do cliente, logo "
            "parecido demais com um real, review inventada, violeta/lavanda na "
            "paleta propria.").format(out_line=out_line, stack_line=stack_line)

        return SkillResult("done", message, data)


# registry.py loads handler.py looking for class Skill(BaseSkill).
Skill = Handler
