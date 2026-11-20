---
name: pptx
description: >-
  Cria, lê e edita apresentações PowerPoint (.pptx/.potx): decks de vendas
  e pitch decks, slides institucionais, leitura de conteúdo slide a slide e
  edição de arquivo existente (unzip → ppt/slides/slideN.xml → rezip).
  Leitura via file_processor / python-pptx; criação com python-pptx em
  canvas widescreen 13,33"×7,5" com QA visual obrigatório. Use quando o
  usuário mencionar "powerpoint", ".pptx", "deck", "slides", "apresentação"
  ou pedir extração de conteúdo de slides.
version: 1.0.0
intents:
  - "criar um powerpoint"
  - "montar um deck"
  - "criar slides"
  - "editar esse pptx"
  - "ler esse pptx"
  - "fazer uma apresentação"
  - "extrair o conteúdo dos slides"
params:
  type: object
  properties:
    action:
      type: string
      enum: [read, create, edit]
      description: >-
        read: ler conteúdo dos slides; create: novo deck (exige deck_plan);
        edit: alterar deck existente via OOXML.
    path:
      type: string
      description: Caminho do .pptx (obrigatório em read e edit).
    out:
      type: string
      description: Pasta de saída para o novo deck em create.
    deck_plan:
      type: string
      description: >-
        Outline em texto do deck para create: mensagem por slide,
        seções, dados/tabelas que entram, público e tom.
supported_os: [windows, any]
required_capabilities: [filesystem]
---

# Apresentações (pptx)

Um `.pptx` é um ZIP de XMLs. Escolha a abordagem pela tarefa:

| Tarefa | Ferramenta |
|---|---|
| **Ler** conteúdo | Tool nativa **`file_processor`** (lê pptx slide a slide) ou `python-pptx` detalhado |
| **Criar** um deck | `python-pptx` — construa como deck estruturado (tema → layouts → slides), veja footguns |
| **Editar** deck existente ou partir de template | unzip → editar `ppt/slides/slideN.xml` → rezip |

Tudo roda no Python do app (`python-pptx`, `Pillow`). **Não há pptxgenjs, scripts npm nem validate.py no JINX** — esse tooling do upstream foi descartado; a checagem aqui é de QA visual + conteúdo. **LibreOffice (`soffice`) para converter slides em imagem é DEPENDÊNCIA EXTERNA OPCIONAL** — pode não estar instalada; sem ela, a revisão acontece dentro do próprio PowerPoint ou com os olhos do usuário.

## Ler um deck

1. Rápido: `file_processor` sobre o .pptx — devolve o texto slide a slide.
2. Detalhado com python-pptx — itere `prs.slides` e, por slide, `slide.shapes`:
   cada shape com `shape.has_text_frame`/`text_frame.text`, `shape.has_table`
   (células linha a linha), `shape.shape_type`, posição `left/top/width/height`
   (EMU), `slide.has_notes_slide` e `notes_slide.notes_text_frame.text`.
3. Para .potx (template), mesmo caminho de leitura; edite mantendo a extensão.

## Criar com python-pptx — footguns essenciais

Usou exemplos de gerador de deck? Estes footguns (vindos de bibliotecas JS do upstream) valem diretamente no python-pptx:

- **Defina o tamanho do slide ANTES de adicionar slides.** O default do template é 10"×7,5" (4:3). Para widescreen 16:9:
  ```python
  from pptx import Presentation
  from pptx.util import Inches, Pt, Emu
  from pptx.dml.color import RGBColor
  prs = Presentation()
  prs.slide_width = Inches(13.333)   # 13,33" × 7,5" widescreen
  prs.slide_height = Inches(7.5)
  ```
- **Coordenadas fora do canvas NÃO clampam:** o shape é gravado fora do slide
  e simplesmente não aparece. Confira `0 ≤ left`, `left+width ≤ slide_width` etc.
  para todo shape composto.
- **Cores em hex SEM `#`:** `RGBColor.from_string("FF0000")` — 6 dígitos.
  Transparência não vai no hex: use alpha do efeito correspondente.
- **Text boxes têm margem interna:** quando o texto precisa alinhar com uma
  forma/linha/ícone no mesmo x, zere `text_frame.margin_left = 0`
  (e a margem equivalente). `text_frame.word_wrap = True` para evitar
  linha infinita.
- **Listas:** herde os bullets do placeholder/layout — só sobrescreva com
  `buChar`/`buAutoNum`/`buNone` na edição XML cru quando necessário. **Nunca
  ponha `•` literal** no texto (renderiza em dobro). Um parágrafo `<a:p>`
  por item, nunca itens concatenados.
- **Notas do apresentador:** `slide.notes_slide.notes_text_frame.text = "..."` — texto simples, uma passada por slide; nunca numa caixa de texto no slide.
- **Gráficos nativos:** use a API de `chart` do python-pptx (`CategoryChartData` + `slide.shapes.add_chart`) para tudo que o PowerPoint grafica. Sem séries nativas (Sankey, rede), entre com imagem — mas trendlines/erros: calcule a série extra, não rasterize.
- **Gráfico default sai pelado:** sempre dê título, cores da paleta, formato dos eixos e legenda coerentes com o deck; num gráfico de barra empilhada, rótulos na posição interna (`ctr`/`inEnd`/`inBase`) — `outEnd` corrompe o arquivo.
- **`text_frame.text = "..."` em shape existente destrói a formatação** (colapsa num run único sem estilo): em deck já criado, atribua em `run.text`, nunca no frame inteiro.
- **Estrutura via layouts do template:** prefira layouts/placeholders do template mestre (`prs.slide_layouts[i]`) — placeholder de título/corpo, não caixas soltas; placeholder não preenchido = inserir posição/tamanho do próprio.

## Conteúdo e fluxo do deck

- **Uma mensagem por slide.** Estrutura piramidal: mensagem principal no começo, resumo executivo que antecipa as seções, seções, conclusão com próximos passos.
- Dimensione pela fala: ~1,5–2 min por slide (deck ao vivo pede menos palavras; deck para leitura carrega a narrativa sozinha).
- **Todo slide precisa de elemento visual** (imagem, gráfico, ícone, forma) — slide só de bullets é esquecível; e **nunca repita o mesmo layout** em todos.
- Paleta específica do assunto, com dominância: uma cor dominante (60–70%), 1–2 tons de apoio, um acento pontual. **Nunca** use linhas de acento sob títulos nem barras/faixas decorativas — marca de slide gerado por IA; separe blocos com fundo levemente tingido, sombra ou ícone.
- **Fundos claros/escuros em "sanduíche"** (capa e conclusão escuras, conteúdo claro) ou tudo escuro.
- Tipografia (fontes instaladas com Office, renderizam fiel no QA): Arial, Calibri, Cambria, Times New Roman, Courier New. **Nunca use Aptos**. Títulos 36–44pt bold, cabeçalho de seção 20–24pt, corpo 14–16pt (mínimo absoluto 14pt — corte texto antes de encolher), legendas 10–12pt.
- Corpo alinhado à esquerda; centro só em títulos. Margens ≥ 0,5"; espaço entre blocos 0,3–0,5" consistente.

## Editar deck existente (OOXML)

```
1. descompacte com zipfile.extractall("unpacked")  (arquivo externo = não confiável)
2. ESTRUTURA ANTES do conteúdo: adicionar/duplicar/excluir/reordenar slides
   editando <p:sldIdLst> em ppt/presentation.xml — e só depois edite o conteúdo
3. duplicar slide = copiar slideN.xml + registrar em ppt/presentation.xml E
   ppt/_rels/presentation.xml.rels E [Content_Types].xml (ou duplique via
   python-pptx copiando shape a shape para um slide novo)
4. edite textos em ppt/slides/slideN.xml in place — sem reformatar ou
   deixar o XML "bonito";
   texto com espaço inicial/final precisa xml:space="preserve" no <a:t>
5. rezipe TODOS os arquivos preservando [Content_Types].xml e _rels/, com extensão .pptx (ou .potx se era template)
```

- Shapes de template ≠ itens reais: se o template mostra 4 pessoas e você tem 3, apague o grupo inteiro do 4º (imagem + caixas), não só o texto.
- Bullets herdam do layout; só crie `<a:buChar>`/`<a:buAutoNum>`/`<a:buNone>` para sobrescrever.
- **Ao remover um shape animado, apague também o `<p:timing>` do slide** (as animações vão junto) — senão o PowerPoint oferece "reparar" o arquivo.
- python-pptx NÃO duplica slides (`add_slide(layout)` é a única entrada), não preserva formatação via `text_frame.text=`, e não lê SVG/EMF de arte de template.

## QA visual — OBRIGATÓRIO

**Overflow de texto é o defeito nº 1** — verifique primeiro, sempre:

- texto cortado numa caixa ou estourando o slide; caixa estreita demais com quebra excessiva;
- sobreposições (texto atravessando formas, linhas cruzando palavras);
- gaps desiguais (área grande vazia num canto, aperto no outro) e blocos a menos de 0,3";
- margens < 0,5" e colunas desalinhadas entre slides do mesmo tipo;
- contraste fraco (texto claro em fundo claro, ícone escuro em fundo escuro — texto E ícones);
- placeholder esquecido (lorem, TODO, "Clique para adicionar", "X" de template);
- número/figura quebrado entre linhas ("26" numa linha, "M" na outra); título terminando com ponto; elemento decorativo do template deslocado após troca de texto.

Compare slides de mesmo tipo entre si, não só cada slide consigo.

**Como enxergar os slides:**

- **Com LibreOffice instalado (dependência externa opcional):** `soffice --headless --convert-to pdf deck.pptx` e rasterize o PDF (pdftoppm, também opcional) — inspecione TODAS as páginas e corrija, re-renderizando só o que mudou. Sem pdftoppm, peça ao usuário que abra o PDF.
- **Sem LibreOffice:** não há prévia automática. Feche o circuito com o usuário: abra o deck no PowerPoint (`start deck.pptx` no Windows) e pergunte slide a slide se há algo cortado/encavalado antes de declarar pronto.

**QA de conteúdo:** releia o texto extraído (file_processor) buscando typos, ordem errada e placeholder esquecido — sem validate.py no JINX, essa revisão é manual.

## Não fazer

- Adicionar slides antes de definir `prs.slide_width/height`.
- `#` no hex de cor; coordenadas sem conferir limites do slide.
- `•` literal; `text_frame.text =` em arquivo existente; itens de lista concatenados num parágrafo.
- Linha de acento sob título; faixa/barra decorativa; fundo bege default; azul genérico.
- Declarar deck pronto sem QA visual (conversão opcional + conferência do usuário) e sem checar placeholders esquecidos.
- Presumir LibreOffice/pdftoppm — dependências externas opcionais.
