---
name: img-to-html
description: >-
  Recria um mock de UI (imagem) como HTML + CSS + JS estáticos (sem framework),
  em etapas com aprovação do usuário: wireframe ASCII tipado com plano → fundo
  completo → componentes com fontes → assets restantes → revisão final.
version: 1.0.0
intents:
  - "img to html"
  - "recriar essa tela"
  - "recriar esse mock como html"
  - "converter imagem em html"
  - "img-to-html"
params:
  type: object
  properties:
    image:
      type: string
      description: Path ou URL da imagem de referência (PNG/JPG/WebP) do mock de UI.
    slug:
      type: string
      description: Nome curto do projeto em kebab-case. Se ausente, deriva do nome do arquivo.
supported_os: [windows, any]
required_capabilities: [filesystem]
---

# Img → HTML

## O que é

Transforma um **mock de interface** (PNG/JPG/WebP) numa **recriação HTML** fiel, passo a passo.

**Entrada:** uma imagem de referência (path ou URL, via param `image`). Se faltar, peça.

**Saída:** pasta `design-systems/<slug>/` com a referência copiada, o wireframe, o **`index.html`** e uma pasta **`assets/`** com o CSS, o JS e as mídias geradas.

O entrypoint final deve se chamar exatamente **`index.html`**.

`<slug>` = nome curto do mock em kebab-case. Se o usuário não indicar, derive do nome do arquivo ou pergunte.

## Por que em etapas

Recriar a tela inteira de uma vez falha (cores, glass, ícones e fontes misturam erros). O fluxo é **bottom-up**: cada camada só começa depois da anterior **aprovada** pelo usuário. O wireframe define *o que* existe e o plano indica *quando* e *como* implementar cada região.

## Pipeline

```
1. wireframe ASCII tipado + plano     → [usuário aprova]
2. fundo completo (CSS e/ou imagens)  → [usuário aprova]
3. estrutura e componentes + fontes   → [usuário aprova]
4. assets restantes (ícones, imagens) → [usuário aprova, se houver]
5. revisão final integrada            → [usuário aprova]
```

## Gate de aprovação (vale para todas as etapas)

Ao terminar uma etapa:

1. Mostre o resultado (path e/ou screenshot no browser).
2. Pergunte se está correto / se mudaria algo.
3. **Pare.** Não inicie a etapa seguinte.

Só avance com confirmação explícita ("aprovado", "pode seguir", "ok"). Se o usuário pedir correção: edite, mostre de novo, aguarde nova aprovação.

A aprovação do plano autoriza a sequência proposta, sem substituir os gates de implementação. Sem assets restantes, omita a etapa 4.

## Layout da pasta

```
design-systems/<slug>/
  reference.[ext]      # cópia da imagem de entrada
  wireframe.txt        # planta tipada + plano apresentado junto
  index.html           # markup — só estrutura, sem <style>/<script> inline
  assets/
    styles.css         # todo o CSS
    app.js             # todo o JS (só se o mock precisar de comportamento)
    crops/             # recortes da reference
    *.png / *.mp4 …    # imagens, ícones, vídeos gerados
```

### Stack: HTML + CSS + JS separados

**Sem build, sem bundler, sem framework, sem `node_modules`, sem dev server** — abre com `start index.html` (Windows) e funciona.

- `index.html` carrega os outros dois: `<link rel="stylesheet" href="assets/styles.css">` no `<head>` e `<script src="assets/app.js" defer></script>`.
- **Nada de `<style>`/`<script>` inline**, nada de `style="…"`. Todo CSS vive em `assets/styles.css`.
- Um `styles.css` só. Acima de ~1500 linhas, quebre por região mas o default é um arquivo.
- CSS puro com **custom properties** no `:root` (cores, radius, sombras, tipografia).
- Cada região do wireframe vira uma **classe CSS** (`.nav`, `.hero`, `.card`); cada tag tipada vira utilitária (`.h1`, `.btn`). Mesmo id no wireframe = mesma classe.
- Conteúdo repetido é escrito direto no HTML; só crie `app.js` para comportamento real.
- Paths sempre relativos: `assets/{id}.png`.

---

## Etapa 1 — Wireframe ASCII tipado + plano

Objetivo: a **planta estrutural** da tela, com plano curto de implementação por região.

1. Criar `design-systems/<slug>/` e copiar a imagem para `reference.[ext]` (o handler desta skill já faz isso).
2. Gerar o wireframe ASCII tipado: caixas por região com ids estáveis (`nav`, `hero`, `card`…), tags tipadas (`[h1:]`, `[t2:]`, `[btn:]`, `[lnk:]`, `[ico:]`, `[img:]`, `[av:]`) e textos reais. Leitura ilegível = marcar e perguntar, não inventar.
3. Manter o ASCII em `wireframe.txt` como contrato canônico; não usar SVG nesta etapa.
4. Plano na mensagem: tabela por região com **etapa** e **técnica** prevista. Classificar imagens por **função**: fundo da tela → 2; fundo de componente → 3; conteúdo/ícone/avatar → 4.
5. **Gate único** para estrutura + sequência/técnicas.

## Etapa 2 — Fundo completo

1. Criar esqueleto mínimo de `index.html` + `assets/styles.css` (reset curto + `:root`).
2. Recriar o fundo completo (CSS, imagem ou camadas). Gerar imagens de fundo agora, não na etapa 4.
3. Ajustar posição, escala, recorte, transparência e mistura. Comparar com a referência no browser.
4. **Gate.**

## Etapa 3 — Estrutura e componentes + fontes

1. Markup no `index.html`, estilo em `assets/styles.css`: primeiro o chrome (nav/top bar/sidebar), depois cada tipo de card e as demais regiões.
2. **Fontes antes do ajuste fino:** para cada tag distinta, família + peso (Google Font mais próxima, informando a aproximação), aplicar `<link>` no HTML e confirmar carregamento.
3. Iterar medindo, não chutando: cores amostradas, gradientes (ângulo + stops), glass vs opaco, bordas/rim light, glow/sombras, radius, padding, tipografia. Nav primeiro, depois card a card, compare crop vs recreate.
4. **Gate.**

## Etapa 4 — Assets restantes

Implementar `[ico:]`/`[img:]`/`[av:]` pendentes. Gerar em lotes (assets independentes em paralelo). Para ícones, PNG com fundo transparente. Não regenerar assets já aprovados. Sem pendências, omitir a etapa. **Gate.**

## Etapa 5 — Revisão final integrada

1. Screenshot da tela completa vs referência, mesmo viewport, fontes e assets carregados.
2. Corrigir integração: sobreposição, recortes, alinhamentos, quebras, espaçamentos.
3. Conferir paths relativos e comportamentos. Informar aproximações reais.
4. Mostrar tela completa e arquivos finais → **Gate.**

## Não fazer

- Pular gates ou "adiantar" várias etapas num único turno.
- Inventar textos ilegíveis no wireframe; marque e pergunte.
- Marcar nav ativo como `[lnk:]` (use `[btn:]`).
- Placeholder genérico quando o plano pede asset gerado da ref.
- CSS inline — todo estilo vai para `assets/styles.css`.
- Criar `package.json`, bundler, framework ou espalhar arquivos fora de `assets/`.
