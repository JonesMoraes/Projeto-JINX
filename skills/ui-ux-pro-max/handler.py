"""Handler for the ui-ux-pro-max skill.

Builds a structured design brief from the priority table embedded below.
Intentionally lean: no file I/O beyond validation, no upstream database,
deterministic output. The agent applies the body of SKILL.md to the task.
"""
from __future__ import annotations

from skills.base import BaseSkill, SkillContext, SkillResult

# Domain -> abbreviated category keys from the upstream database. The full
# rule text lives in SKILL.md's priority table; these keys only route focus.
_DOMAINS: dict[str, tuple[str, ...]] = {
    "accessibility": ("contrast", "alt-text", "keyboard", "aria"),
    "interaction": ("touch-size", "spacing", "loading-feedback"),
    "performance": ("image-format", "lazy-loading", "cls-budget"),
    "style": ("product-fit", "consistency", "svg-icons"),
    "product": ("product-fit", "audience", "platform"),
    "layout": ("mobile-first", "viewport", "no-horizontal-scroll"),
    "typography": ("base-size", "line-height", "font-pairings"),
    "color": ("semantic-tokens", "contrast", "accessible-pairs", "dark-mode"),
    "animation": ("timing", "meaningful-motion", "reduced-motion", "easing"),
    "forms": ("visible-labels", "inline-errors", "helper-text", "progressive-disclosure"),
    "navigation": ("back-behavior", "bottom-nav-limit", "deep-linking"),
    "charts": ("legends", "tooltips", "accessible-colors"),
    "icons": ("svg-icons", "decorative-aria-hidden", "button-labels"),
    "landing": ("hero-structure", "social-proof", "call-to-action"),
}

_CATEGORIES: tuple[dict, ...] = (
    {
        "priority": 1,
        "category": "accessibility",
        "impact": "CRITICAL",
        "domains": ("accessibility", "icons"),
        "key_checks": ("contraste >= 4.5:1", "alt text", "navegacao por teclado",
                       "aria-labels", "anel de foco visivel"),
        "anti_patterns": ("remover anel de foco", "botao so de icone sem label",),
    },
    {
        "priority": 2,
        "category": "touch_interaction",
        "impact": "CRITICAL",
        "domains": ("interaction",),
        "key_checks": ("area minima 44x44px", "espacamento >= 8px entre alvos",
                       "feedback de carregamento"),
        "anti_patterns": ("depender so de hover", "mudanca de estado instantanea (0ms)",),
    },
    {
        "priority": 3,
        "category": "performance",
        "impact": "HIGH",
        "domains": ("performance",),
        "key_checks": ("WebP/AVIF", "lazy loading", "espaco reservado (CLS < 0.1)"),
        "anti_patterns": ("layout thrashing", "cumulative layout shift",),
    },
    {
        "priority": 4,
        "category": "style_selection",
        "impact": "HIGH",
        "domains": ("style", "product"),
        "key_checks": ("estilo coerente com o tipo de produto", "consistencia visual",
                       "icones SVG (nunca emoji)"),
        "anti_patterns": ("misturar flat e skeuomorfico ao acaso", "emoji como icone",),
    },
    {
        "priority": 5,
        "category": "layout_responsive",
        "impact": "HIGH",
        "domains": ("layout",),
        "key_checks": ("breakpoints mobile-first", "meta viewport",
                       "sem scroll horizontal"),
        "anti_patterns": ("scroll horizontal", "container fixo em px", "desabilitar zoom",),
    },
    {
        "priority": 6,
        "category": "typography_color",
        "impact": "MEDIUM",
        "domains": ("typography", "color"),
        "key_checks": ("base 16px", "line-height 1.5", "tokens de cor semanticos"),
        "anti_patterns": ("corpo < 12px", "cinza sobre cinza", "hex cru nos componentes",),
    },
    {
        "priority": 7,
        "category": "animation",
        "impact": "MEDIUM",
        "domains": ("animation",),
        "key_checks": ("timing com contexto", "movimento que comunica significado",
                       "continuidade espacial", "respect prefers-reduced-motion"),
        "anti_patterns": ("uma duracao para tudo", "animar width/height", "sem reduced-motion",),
    },
    {
        "priority": 8,
        "category": "forms_feedback",
        "impact": "MEDIUM",
        "domains": ("forms",),
        "key_checks": ("labels visiveis", "erro junto ao campo", "texto de ajuda",
                       "revelacao progressiva"),
        "anti_patterns": ("placeholder como label", "erro so no topo do formulario",
                          "form gigante de uma vez",),
    },
    {
        "priority": 9,
        "category": "navigation",
        "impact": "HIGH",
        "domains": ("navigation",),
        "key_checks": ("voltar previsivel", "bottom nav <= 5 itens", "deep linking"),
        "anti_patterns": ("navegacao sobrecarregada", "voltar quebrado", "sem deep links",),
    },
    {
        "priority": 10,
        "category": "charts_data",
        "impact": "LOW",
        "domains": ("charts",),
        "key_checks": ("legendas", "tooltips", "cores acessiveis"),
        "anti_patterns": ("confiar so na cor para comunicar",),
    },
)


class Handler(BaseSkill):
    async def run(self, params: dict, ctx: SkillContext) -> SkillResult:
        task = str(params.get("task", "")).strip()
        if not task:
            return SkillResult("failed", "O parametro 'task' e obrigatorio.")

        stack = str(params.get("stack", "")).strip().lower()
        domain = str(params.get("domain", "")).strip().lower()
        project_name = str(params.get("project_name", "")).strip()

        if domain and domain not in _DOMAINS:
            return SkillResult(
                "failed",
                "Dominio desconhecido: {!r}. Validos: {}.".format(
                    domain, ", ".join(sorted(_DOMAINS))))
        if domain:
            brief = [cat for cat in _CATEGORIES if domain in cat["domains"]]
            focus = f"categorias do dominio {domain!r}"
        else:
            brief = list(_CATEGORIES)
            focus = "todas as categorias, em ordem de prioridade"

        priorities = {
            "priority": [cat["priority"] for cat in brief],
            "category": [cat["category"] for cat in brief],
            "impact": [cat["impact"] for cat in brief],
            "key_checks": [list(cat["key_checks"]) for cat in brief],
            "anti_patterns": [list(cat["anti_patterns"]) for cat in brief],
        }
        data = {
            "task": task,
            "project_name": project_name or None,
            "stack": stack or None,
            "domain_filter": domain or None,
            "valid_domains": sorted(_DOMAINS),
            "design_brief": priorities,
            "domain_keys": dict(_DOMAINS),
            "rule": ("busca sem resultado: NAO invente — reforce a consulta uma vez "
                     "e, se persistir, use os defaults da tabela e diga ao usuario "
                     "que usou defaults embutidos"),
        }

        stack_line = stack if stack else (
            "DETETE a stack do projeto (package.json, pubspec.yaml, *.xcodeproj, "
            "composer.json); se nada for detectavel e importar, pergunte — nunca assuma")
        name_line = project_name or "(sem nome informado)"

        message = (
            "Brief de design montado para: {task}. Escopo: {focus}.\n"
            "\n"
            "FLUXO DE TRABALHO (4 passos, com gate de aprovacao entre eles):\n"
            "1. DETECTAR A STACK: {stack_line}. Mostre o que detectou e o tipo de "
            "produto — aguarde aprovacao explicita antes da etapa seguinte.\n"
            "2. GERAR DESIGN SYSTEM: defina padrao, estilo, paleta, tipografia e "
            "efeitos a partir da tabela de prioridades 1->10 da SKILL.md; registre "
            "como tokens semanticos (color.primary, font.heading), nunca hex cru. "
            "Mostre a proposta e aguarde aprovacao antes de escrever codigo.\n"
            "3. CONSULTAS FOCAIS POR DOMINIO: para cada preocupacao (form, "
            "navegacao, acessibilidade), aplique as checagens da categoria "
            "correspondente, uma preocupacao por vez.\n"
            "4. GUIDELINES DA STACK: so depois, adapte as decisoes aos padroes "
            "idiomaticos da stack detectada (next/image, prefers-reduced-motion, "
            "aria-* nativos).\n"
            "\n"
            "REGRAS: prioridade 1->10 decide onde comecar; numa resposta vazia de "
            "busca NAO invente — reforce uma vez e, se persistir, use os defaults e "
            "diga ao usuario que usou defaults embutidos.").format(
                task=task, focus=focus, stack_line=stack_line)

        return SkillResult("done", message, data)


# registry.py loads handler.py looking for class Skill(BaseSkill).
Skill = Handler
