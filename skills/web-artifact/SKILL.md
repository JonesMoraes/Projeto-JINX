---
name: web-artifact
description: >-
  Cria mini-apps web complexos e multi-componente como HTML + CSS + JS
  estáticos (sem node, npm ou bundler — abre com `start index.html`), com
  estado, múltiplas visões/rotas em hash e componentes compostos, ou
  opcionalmente React 18 via CDN como fallback. Use para artefatos web
  elaborados que rodam no browser local. NÃO use para página simples de uma
  tela — essa, escreva o HTML direto.
version: 1.0.0
intents:
  - "criar um app web"
  - "montar um mini-app"
  - "criar um dashboard em html"
  - "criar um artifact web"
  - "fazer um app com telas"
  - "montar um web app complexo"
params:
  type: object
  properties:
    description:
      type: string
      description: >-
        Descrição do que o app faz: funcionalidades, visões/telas, dados e
        interações. É o contrato do que será construído.
    target:
      type: string
      description: >-
        Pasta de saída. Default: web-artifacts/<slug>/ na pasta base do JINX
        (slug derivado da description).
    framework:
      type: string
      enum: [vanilla, react-cdn]
      default: vanilla
      description: >-
        vanilla (default): HTML+CSS+JS estáticos separados. react-cdn:
        React 18 UMD + Babel standalone via CDN — fallback que exige
        internet ao abrir e NÃO roda offline.
supported_os: [windows, any]
required_capabilities: [filesystem]
---

# Web artifacts (HTML + CSS + JS estáticos)

## O que é (e o que NÃO é)

**Sem nada de ambiente node.** O JINX não tem node/npm e não faz build — a analogia certa é a skill **img-to-html**: arquivos estáticos que abrem com `start index.html` (Windows) e funcionam.

**Não é para página simples.** Quando o pedido é uma página simples de uma tela, **NÃO use esta skill — escreva o HTML direto**. Esta skill existe para **artefatos complexos**:

- múltiplos componentes e telas;
- estado que muda com as interações (filtros, carrinho, formulários em série);
- navegação entre visões (rotas);
- dados derivados que reagem a entradas (gráfico filtrável, editor com undo...).

## Inicializar a estrutura

Escolha **uma** das formas (o handler desta skill já cria o esqueleto):

**A. Um único `index.html`** (melhor para artefato pequeno-médio que precisa ser um único arquivo compartilhável): tudo dentro — `<style>` no `<head>` e `<script>` no fim do `<body>`, sem build.

**B. Pasta separada (o padrão desta skill, espelha img-to-html):**

```
web-artifacts/<slug>/
  index.html          # só markup, sem <style>/<script> inline
  assets/
    styles.css        # todo o CSS
    app.js            # todo o JS
```

Regras (iguais às da img-to-html):

- Sem build, sem bundler, sem framework, sem `node_modules`, sem dev server.
- `index.html` carrega `assets/styles.css` via `<link>` e `assets/app.js` com `defer` — **nada de `<style>`/`<script>` inline**, nada de `style="..."`.
- Um `styles.css` só; um `app.js` só. Paths sempre relativos.
- CSS puro com custom properties no `:root` (cores, radius, sombras, tipografia).

## Estado, telas e componentes (vanilla)

- **Estado num único objeto JS** (ex.: `const state = { filtro: null, itens: [] }`) e **uma função `render()`** por tela/visão-evento que redesenha o alvo — isso reproduz a reatividade do React sem framework.
- **Rotas:** hash routing nativo — `location.hash` (`#visao1`, `#visao2`) + `window.addEventListener("hashchange", render)`. Cada visão é uma função que recebe o container e o estado.
- **Componentes = funções que retornam strings HTML** (template literal) com um `data-*` ou classe por elemento interativo; eventos via delegação (`container.addEventListener("click", ...)` checando `event.target.closest("[data-acao]")`) — um listener, não um por item.
- Dados de exemplo: um array de objetos no topo do `app.js`, claramente marcado como fake — o usuário troca depois.
- Persistência local: `localStorage` se o artefato precisa sobreviver ao fechar (salve no lugar e avise o usuário).

## framework react-cdn — fallback com limitações

Quando o usuário pede React explicitamente (ou o app pede componentes na mão que não valem reimplementar), o `index.html` usa **React 18 UMD + Babel standalone via CDN** — já é a base que o handler cria:

- `<script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>` + `react-dom` equivalente + `<script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>` e o código em `<script type="text/babel">`.
- **Avise o usuário: exige internet ao abrir e dá tela branca offline.** Não é fallback offline — sem internet, vira outra coisa (vanilla).
- Use hooks (`useState`/`useEffect`) de forma simples — uma função por componente, sem TS.

Quando em dúvida, **vanilla vence**: o app estático separado é mais rápido, funciona offline e não quebra com CDN fora do ar.

## Design — contraste com "AI slop"

O original lista os vícios; aqui sem Tailwind, vale aplicar à mão:

- **Nada de layout inteiro centrado, gradiente roxo, cantos arredondados uniformes e fonte Inter** — os vícios do original valem à mão: escolha uma paleta de 2–3 cores específica do assunto, espaçamentos consistentes e tipografia com hierarquia real. Referência de componentes/profissional: https://ui.shadcn.com/docs/components — inspire-se na estrutura (botões, cards, diálogos) e recrie o essencial à mão; não há npm.
- Contraste de verdade: texto e ícones legíveis sobre o fundo em toda tela.

## Desenvolver, apresentar, (só então) testar

1. **Desenvolva** segundo a description do usuário — sem reescrever o escopo.
2. **Apresente o artefato terminado** antes de qualquer teste (`start index.html` abre no browser do usuário — é ele quem vê primeiro).
3. **Teste só depois, se pedido ou se houver problema reportado** — testar antes só atrasa a primeira visão do resultado. Se testar, faça no browser e nomeie os passos que reproduzem o que passou.

## Não fazer

- Página simples de uma tela dentro desta skill — é HTML direto, sem pasta e sem plano.
- node/npm/bundler/`package.json`/framework instalado — não existem no JINX.
- `<style>`/`<script>` inline, `style="..."` espalhado no markup (na estrutura B).
- React via CDN para um artefato que roda offline sem avisar a limitação.
- Testar antes de apresentar; apresentar sem dizer como abrir (`start index.html`).
