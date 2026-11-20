"""Handler da skill web-artifact.

Cria o esqueleto do artefato web (pasta + index.html + assets sem build)
e devolve o passo a passo para o agente desenvolver o app descrito.
Desenvolver o app em si é do agente, conforme o SKILL.md.
"""
from __future__ import annotations

import os
import unicodedata
from pathlib import Path
from typing import Any

from skills.base import BaseSkill, SkillContext, SkillResult


def _slugify(value: str, fallback: str = "artifact") -> str:
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


VANILLA_INDEX = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__SLUG__</title>
  <link rel="stylesheet" href="assets/styles.css">
</head>
<body>
  <div id="app"></div>
  <!-- nada de <style>/<script> inline: todo CSS em assets/styles.css,
       todo JS em assets/app.js -->
  <script src="assets/app.js" defer></script>
</body>
</html>
"""

_STYLES = """:root {
  /* paleta específica do assunto — 2-3 cores, evite roxo/Inter/AI slop */
  --cor-fundo: #ffffff;
  --cor-texto: #1a1a1a;
  --cor-acento: #0b5394;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: Arial, sans-serif;   /* fonte instalada; evite Inter */
  background: var(--cor-fundo);
  color: var(--cor-texto);
}
"""

_APP = """// app.js — estado único + render() por visão + hash routing
"use strict";

const state = {
  // dados de exemplo (fake) — troque pelos dados reais
  itens: [],
};

function render() {
  const app = document.getElementById("app");
  if (!app) return;
  // uma função por visão; rota corrente pelo hash (#minha-visao)
  app.innerHTML = "<h1>" + location.hash.replace("#", "") + "</h1>";
}

window.addEventListener("hashchange", render);
// delegação de eventos: um listener, checando data-acao
document.addEventListener("click", (event) => {
  const alvo = event.target.closest("[data-acao]");
  if (!alvo) return;
  // ... atualize state e chame render()
});
render();
"""

_REACT_INDEX = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__SLUG__</title>
  <!-- FALLBACK NÃO-OFFLINE: exige internet ao abrir; sem rede, tela branca -->
  <script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
  <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
  <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
  <link rel="stylesheet" href="assets/styles.css">
</head>
<body>
  <div id="root"></div>
  <script type="text/babel">
    // React 18 via CDN — um componente por função, hooks simples (useState)
    function App() {
      const [visao] = React.useState("inicial");
      return <h1>__SLUG__ — {visao}</h1>;
    }
    ReactDOM.createRoot(document.getElementById("root"))
      .render(<App />);
  </script>
</body>
</html>
"""


class Handler(BaseSkill):
    async def run(self, params: dict[str, Any], ctx: SkillContext) -> SkillResult:
        description = str(params.get("description", "")).strip()
        if not description:
            return SkillResult(
                status="failed",
                message="Informe 'description' com o que o app faz: "
                        "funcionalidades, visões/telas, dados e interações.",
            )
        framework = str(params.get("framework", "vanilla") or "vanilla").strip().lower()
        if framework not in {"vanilla", "react-cdn"}:
            return SkillResult(
                status="failed",
                message="framework inválido. Use 'vanilla' (default) ou 'react-cdn'.",
            )

        slug = _slugify(description.splitlines()[0])
        raw_target = str(params.get("target", "")).strip()
        base = Path(raw_target).expanduser() if raw_target else _base_dir(ctx) / "web-artifacts" / slug

        index_name = "index.html"
        conflict = (base / index_name).exists()
        (base / "assets").mkdir(parents=True, exist_ok=True)

        if framework == "react-cdn":
            index_html = _REACT_INDEX.replace("__SLUG__", slug)
            warning = (" ATENÇÃO: react-cdn é FALLBACK NÃO-OFFLINE — exige "
                       "internet ao abrir; prefira vanilla se o usuário precisa "
                       "rodar offline.")
        else:
            index_html = VANILLA_INDEX.replace("__SLUG__", slug)
            warning = ""
        (base / index_name).write_text(index_html, encoding="utf-8")
        (base / "assets" / "styles.css").write_text(_STYLES, encoding="utf-8")
        (base / "assets" / "app.js").write_text(_APP, encoding="utf-8")

        try:
            if os.name == "nt":
                os.startfile(str(base))  # noqa: S606 — best-effort
        except Exception:  # noqa: BLE001
            pass

        message = (
            f"Esqueleto {framework} criado em {base} "
            f"({'index.html já existia — não sobrescreva o conteúdo anterior sem aprovação' if conflict else 'pasta nova'}).{warning} "
            "Agora desenvolva o app conforme 'description', pelo SKILL.md: "
            "1) estado num único objeto JS + função render() por visão, "
            "rotas por hash (hashchange) e eventos por delegação — tudo em "
            "assets/app.js (na variante react-cdn, JSX no bloco "
            "text/babel do index.html); "
            "2) CSS completo em assets/styles.css, sem <style>/style= inline — "
            "paleta específica do assunto, nada de layout centrado de fábrica, "
            "gradiente roxo, cantos uniformes e fonte Inter; "
            "3) este artefato serve para pedido COMPLEXO (multi-componente, "
            "estado, rotas) — se a description acordou numa página simples de "
            "uma tela, pare e escreva o HTML direto em vez de seguir o "
            "esqueleto; "
            "4) APRESENTE o artefato terminado ao usuário antes de qualquer "
            "teste (start index.html abre o browser; é ele quem vê primeiro); "
            "teste só depois, se pedido ou se houver problema reportado."
        )
        return SkillResult(
            status="done",
            message=message,
            data={
                "framework": framework,
                "folder": str(base),
                "index": str(base / index_name),
                "has_existing_index": conflict,
                "files": [str(base / index_name),
                          str(base / "assets" / "styles.css"),
                          str(base / "assets" / "app.js")],
            },
        )


# Alias para runtimes que esperam a classe exposta como "Skill".
Skill = Handler
