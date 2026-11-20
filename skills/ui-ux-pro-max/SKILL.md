---
name: ui-ux-pro-max
description: >-
  Inteligência de design UI/UX aplicada a qualquer etapa: criação de telas,
  componentes, direção visual, acessibilidade, layouts responsivos, tipografia,
  cores, forms e charts. Regera antes de codar, revise depois de codar.
version: 1.0.0
intents:
  - "revise o design da interface"
  - "crie o design system do projeto"
  - "melhore a UX dessa tela"
  - "avalie a acessibilidade"
  - "guia de UI para essa stack"
params:
  type: object
  properties:
    task:
      type: string
      description: "O que o usuário pediu (ex.: 'homepage para um spa', 'revisar formulário de cadastro')."
    stack:
      type: string
      description: "Stack detectada no projeto (ex.: react, nextjs, vue, flutter). Não invente: detecte de package.json ou equivalente, ou pergunte."
    domain:
      type: string
      description: "Foco opcional em um domínio: accessibility, interaction, performance, style, layout, typography, animation, forms, navigation, charts."
    project_name:
      type: string
  required:
    - task
supported_os:
  - any
required_capabilities: []
---

# UI/UX Pro Max — inteligência de design

Esta skill condensa a inteligência de design do upstream ui-ux-pro-max em
orientação direta: em vez de consultar um banco de dados local, você **aplica a
tabela de prioridades e as checagens-chave deste documento** para decidir no
que focar e por onde começar.

## Quando aplicar

Use quando a tarefa envolve **estrutura de UI, decisões visuais, padrões de
interação ou qualidade de experiência**: páginas novas, criação/refactor de
componentes, escolha de cor/tipografia/espaçamento/layout, revisão de UI para
acessibilidade e consistência, navegação, animação ou comportamento responsivo.

Pule para trabalho puramente de backend, API/banco, performance não-visual ou
DevOps — a menos que mude **como algo se parece, se move ou é manipulado**.

## Tabela de prioridades 1→10

Siga a ordem de prioridade para decidir qual categoria atacar primeiro. Cada
linha traz as checagens obrigatórias e os anti-padrões a evitar.

| # | Categoria | Impacto | Checagens obrigatórias | Anti-padrões a evitar |
|---|-----------|---------|------------------------|-----------------------|
| 1 | Acessibilidade | CRÍTICO | Contraste ≥ 4.5:1, alt text, navegação por teclado, aria-labels | Remover anel de foco, botão só de ícone sem label |
| 2 | Toque & interação | CRÍTICO | Área mínima 44×44px, espaçamento ≥ 8px, feedback de carregamento | Depender só de hover, mudança de estado instantânea (0ms) |
| 3 | Performance | ALTO | WebP/AVIF, lazy loading, espaço reservado (CLS < 0.1) | Layout thrashing, Cumulative Layout Shift |
| 4 | Seleção de estilo | ALTO | Estilo coerente com o tipo de produto, consistência, ícones SVG (nunca emoji) | Misturar flat e skeuomórfico ao acaso, emoji como ícone |
| 5 | Layout responsivo | ALTO | Mobile-first, meta viewport, sem scroll horizontal | Scroll horizontal, larguras fixas em px, desabilitar zoom |
| 6 | Tipografia & cor | MÉDIO | Base 16px, line-height 1.5, tokens de cor semânticos | Corpo < 12px, cinza sobre cinza, hex cru direto nos componentes |
| 7 | Animação | MÉDIO | Timing com contexto, movimento que comunica, continuidade espacial | Uma duração para tudo, animar width/height, ignorar reduced-motion |
| 8 | Formulários & feedback | MÉDIO | Labels visíveis, erro junto ao campo, texto de ajuda, revelação progressiva | Placeholder como label, erro só no topo, form gigante de uma vez |
| 9 | Navegação | ALTO | Voltar previsível, bottom nav ≤ 5 itens, deep linking | Navegação sobrecarregada, voltar quebrado, sem deep links |
| 10 | Charts & dados | BAIXO | Legendas, tooltips, cores acessíveis | Confiar só na cor para comunicar |

## Fluxo de trabalho (4 passos)

O handler desta skill monta um **brief de design** estruturado. Siga este
fluxo, com um gate de aprovação entre os passos:

1. **Detectar a stack** — procure `package.json` (react/next/vue/svelte/
   nuxt/@angular), `pubspec.yaml` (Flutter), `*.xcodeproj`/`Package.swift`
   (SwiftUI), `composer.json` (Laravel) ou marcadores de React Native. Se não
   achar nada e a stack importar, **pergunte ao usuário; nunca assume stack**.
   → Apresente o que detectou e o tipo de produto; **aguarde aprovação
   explícita antes da etapa seguinte**.
2. **Gerar design system** (obrigatório para páginas/projetos novos) — defina
   padrão, estilo, paleta, tipografia e efeitos a partir da tabela de
   prioridades e do tipo de produto. Registre como tokens semânticos
   (`color.primary`, `font.heading`…), nunca hex cru nos componentes.
   → Mostre a proposta; **aguarde aprovação antes de escrever código**.
3. **Consultas focais por domínio** — para cada preocupação específica
   (formulário, telemetria, navegação), resolva com a(s) categoria(s)
   correspondente(s) da tabela e aplique as checagens. Uma preocupação por vez:
   para acessibilidade, busque um resultado observável por vez ("erro resumido
   junto ao campo"), não uma auditoria genérica.
4. **Guidelines da stack** — só depois, adapte as decisões aos componentes e
   padrões idiomáticos da stack detectada (ex.: `next/image` para lazy loading;
   `prefers-reduced-motion` em CSS; `aria-*` nativos de cada framework).

## Regra da resposta vazia

Quando uma consulta ao repositório upstream ou ao projeto não retorna nada:
1. **NÃO invente.**
2. Tente uma vez com termos mais estreitos ou um domínio explícito.
3. Se ainda vazio, caia na tabela de prioridades acima e diga explicitamente
   ao usuário que usou **defaults embutidos**, não um match do banco
   (ex.: "nenhuma paleta específica para X; usei defaults de SaaS").

Nunca apresente uma resposta vazia como se tivesse retornado dados.

## Banco completo de dados (opcional)

O upstream empacota CSVs pesquisáveis (estilos, paletas de produto, pares de
fontes, ~130 diretrizes UX, ícones, presets de animação, tipos de chart e 22
stacks — mais de 800 KB). **Este porte não carrega esses dados.** Se o usuário
quiser o banco completo, aponte para o repositório upstream de ui-ux-pro-max e
baixe lá; é opcional e não é necessário para aplicar esta skill.

## Antes de entregar UI de app

Passe o checklist: disciplina de ícones/visuais, feedback de interação,
contraste claro/escuro, áreas seguras, acessibilidade, tamanho de toque
44×44 e navegação previsível.
