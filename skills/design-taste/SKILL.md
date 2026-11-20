---
name: design-taste
description: >-
  Skill anti-slop para frontend: constrói sites de empresa de nível
  profissional — copy com voz própria, um sistema visual único, seções medidas
  por telas, fotos reais, micro-interações discretas e checagem em navegador
  real. Use ao construir ou revisar landing page, site de produto, SaaS,
  comércio, hotel, café ou portfolio, e quando o usuário disser que a página
  parece genérica ou "feita por IA".
version: 1.0.0
intents:
  - "crie uma landing page profissional"
  - "refaça o site que parece genérico"
  - "desde que pareça feito de verdade"
  - "revise o visual do site"
  - "polir o design antes de entregar"
params:
  type: object
  properties:
    brief:
      type: string
      description: "Brief do cliente: o que é vendido, para quem, ação principal e material real disponível (logo, fotos, telas, preços)."
    stack:
      type: string
      description: "Stack de destino (static, react, next, vue, svelte, astro, tailwind…). Livre, mas nunca invente: detecte do projeto ou pergunte."
    target:
      type: string
      description: "Pasta de saída opcional para registrar o plano e o checklist."
  required:
    - brief
supported_os:
  - any
required_capabilities: []
---

# Design Taste — site que uma boa empresa entregaria

Diz claramente o que se vende, mostra a coisa real em toda tela e parece feito
**para este cliente** — não de um template, não de uma arte editorial. A régua
são sites de design de referência como figma.com e x.ai: sobrio, direto,
confiante.

As nove regras da casa vencem tudo o mais nesta skill.

## As nove regras da casa

1. **Nada de legenda sob imagem.** Nenhuma imagem, render ou visual recebe
   legenda, explicação ou desculpa. Créditos de foto ficam numa única linha no
   rodapé.
2. **Todo visual renderiza** — nunca um buraco vazio — em **1440, 1024, 768 e
   390** de largura.
3. **Uma seção por tela:** o hero sozinho na primeira tela; cada seção mede
   exatamente uma ou duas telas em 1440×900, sem o h2 da seção seguinte
   aparecendo atrás. Única exceção: uma seção viva de *photo-chapters*, de
   três ou quatro telas, conduzida pelo momento.
4. **Bordas laterais alinhadas:** todo conteúdo alinha nas mesmas linhas
   esquerda e direita (um `.wrap` ou as colunas do grid); nada sobrando para
   um lado; sem scroll lateral.
5. **Micro-animações discretas:** card linkado sobe 2px; foto dá zoom de
   1.02–1.03 dentro da moldura; botão afunda no hover e no clique; sublinhado
   que desenha. O hero entra **uma vez** no carregamento (`data-enter`) —
   nunca animação que repete nem entrada em cada card. Nada de tilt, carrossel
   ou parallax.
6. **Fotos reais e mais delas** onde couber; backgrounds melhores; hero,
   layout e tipografia acima da média. Sem foto do cliente: provação
   (stand-in) do mesmo tipo de coisa, **declarada como tal no relatório** —
   nunca passada pela coisa real.
7. **Ícones de produto em cor cheia:** para uma ferramenta que o produto usa,
   o ícone real e oficial (nunca um desenhado parecido). Diagramas pequenos
   dentro de cards podem ilustrar um fluxo.
8. **Um "momento" por página:** um momento tratado (foto- ou tipografia-
   liderado) por página; dois numa página longa. Efeitos de shader/imersivos
   só em página de assunto técnico (software, jogos, fintech, hardware) —
   nunca em café, padaria, pousada ou loja: essas levam fotos.
9. **Contatos verificáveis sem expor dados reais:** rua e bairro (sem número,
   CEP ou coordenadas), sem CNPJ ou registro, telefone em formato mascarado,
   contatos de teste em domínio `.example`. Fato assumido recebe marca
   `data-assumed` e vai para o relatório.

## Sistema único

**UM par de botões** (primário + secundário), **UM estilo de card**, **UMA
escala de radius**, **UMA escala de títulos**, **UM jeito de link** — e só
isso. Aninhamento no máximo dois níveis. Texto com contraste verificado. No
máximo duas ações no hero, uma ação repetida por tela no máximo.

## Copiar antes de desenhar

Escreva **toda a copy primeiro**: o h1 nomeia a categoria e o comprador (um
jogo: o nome e o gênero); um fato concreto na primeira tela; sempre um
substantivo nos títulos; botões como verbo + objeto. Nada inventado exceto o
nome de marca proposto (e mantido num arquivo ao lado da página) e, num
place, horários e preços plausíveis — sempre marcados como assumidos.

## Verificação: navegador real, não gate automatizado

O upstream verifica a página com gates em Node (gate.mjs, consistency.mjs,
perf.mjs) rodando Chrome headless. **Este porte descarta essa maquinaria.**
No lugar dela:

> Verifique em um **navegador real** — o JINX tem `actions/browser_control` e
> `screen_processor` para capturar telas — nas larguras 1440, 1024, 768 e 390,
> e leia cada captura contra a checklist abaixo.

**Checklist manual de performance** (era `perf.mjs`): peso de imagem
(~≤ 150 KB por fotografia otimizada, Modern formats), sem layout shift
(imagens com `width`/`height` ou `aspect-ratio` reservados; fontes com
`font-display`), sem jank (animação só em `transform`/`opacity`; nada rodando
na scroll), no máximo 4 contextos WebGL ao vivo (nunca em rota não-técnica:
zero).

**Checklist de entrega:**

- Primeira tela: diz o que se vende e para quem, com um fato concreto; o hero
  enche a tela em toda largura; a ação principal cabe nela.
- Uma seção por tela, h2 primeiro e alinhado no topo; nada esparso; nada
  sobrando de um lado.
- Todo visual renderiza em 1440/1024/768/390; sem buraco, sem placeholder
  impresso.
- Nenhuma legenda explicando foto; créditos numa linha só de rodapé.
- Movimento: hero entra uma vez na carga; hover discretos (2px, 1.02–1.03,
  sublinhado desenhado); nada anima porque se rolou a página; com
  `prefers-reduced-motion`, tudo descansa e nada fica escondido.
- Teclado e a11y: todo controle nomeado, alt nas imagens, labels visíveis,
  headings em ordem, `Tab` chega ao skip-link primeiro, anel de foco visível.
- Um sistema: um par de botões, um card, um radius, uma escala de títulos.
- Formulários: labels visíveis, cada erro embaixo do próprio campo, confirmação
  só após envio real.
- Rápido: checklist manual de performance acima sem violações.

## "Never" — nunca

- Card, linha ou tile que faz fade-in ao rolar; fade-in em toda seção;
  parallax em texto; scroll-jacking; piscar aleatório.
- Foto de banco de imagens passando como produto, gente ou local do cliente —
  stand-in **sempre declarado** no relatório; página de produto que nunca
  mostra o produto.
- Logo desenhado parecido demais com um real; review, quote, cliente ou
  número inventado.
- **Violeta ou lavanda** na paleta própria — acento, fundo, gradiente ou
  tint (logo de terceiro real mantém as próprias cores; isso se aplica às
  suas escolhas).
- Copiar código, copy, foto ou efeito-assinatura de um site de referência.

## Procedimento

Siga em quatro passos com gate emitido pelo agente entre eles:

1. Copia única e voz própria → aprovação → 2. Sistema visual (cor, tipo,
   espaço) → aprovação → 3. Seção por seção, cada uma medida por telas →
   aprovação → 4. Checagem final em navegador real + checklist.
