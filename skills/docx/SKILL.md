---
name: docx
description: >-
  Cria, lê, edita e manipula documentos Word (.docx / .dotx): relatórios,
  atas, cartas, currículos, com títulos, sumário (TOC), tabelas, rodapé com
  página, imagens e estilos. Leitura via file_processor / python-docx;
  criação e edição com python-docx; edições profundas via OOXML
  (unpack → word/document.xml → rezip). Use quando o usuário mencionar
  "Word", ".docx", "relatório", "ata", "documento" com formatação, ou pedir
  extrair/reorganizar conteúdo de .docx, find-and-replace ou imagens no
  documento. NÃO use para PDF, planilhas ou Google Docs.
version: 1.0.0
intents:
  - "documento do word"
  - "criar um docx"
  - "criar um documento word"
  - "editar esse docx"
  - "ler esse docx"
  - "fazer um relatório em word"
  - "montar uma ata em word"
  - "colocar sumário no documento"
params:
  type: object
  properties:
    action:
      type: string
      enum: [read, create, edit, ooxml]
      description: >-
        read: extrair conteúdo de um .docx existente; create: novo documento;
        edit: alteração leve em documento existente; ooxml: edição profunda
        via descompactação do XML.
    path:
      type: string
      description: Caminho do .docx (obrigatório em read, edit e ooxml).
    content:
      type: string
      description: >-
        Em create: conteúdo/estrutura desejada (títulos, seções, tabela,
        demais elementos) que orienta o documento a ser gerado.
    out:
      type: string
      description: >-
        Pasta de saída para o novo documento em create. Se ausente, usa a
        pasta base do JINX (jinx_home) ou o diretório corrente.
supported_os: [windows, any]
required_capabilities: [filesystem]
---

# Documentos Word (docx)

Um `.docx` é um ZIP de XMLs. Escolha a abordagem pela tarefa:

| Tarefa | Ferramenta |
|---|---|
| **Ler** conteúdo | Tool nativa `file_processor` (actions/file_processor.py lê docx) ou `python-docx` detalhado |
| **Criar** um documento novo | `python-docx` — veja os footguns abaixo |
| **Editar** trechos de texto de um documento existente | `python-docx` (atribua em `run.text`, nunca em `text_frame.text`) |
| **Edição OOXML profunda** (redlining, campos, XML que python-docx não expõe) | unpack → editar `word/document.xml` → rezip |

Tudo roda no Python do app: `python-docx` já está disponível (e `Pillow` para imagens). Não existe pandoc no JINX: **pandoc, LibreOffice e pdftoppm são dependências EXTERNAS opcionais** — se o usuário as tiver instalado, podem servir para converter `.doc` legado ou renderizar prévia; nunca presuma que existem.

## Ler um documento

1. Rápido: use a tool nativa **`file_processor`** sobre o caminho do `.docx` — ela devolve o texto.
2. Estrutura completa (estilos, tabelas, seções, imagens): `python-docx` —
   itere `document.paragraphs` (com `p.style.name` e `p.text`),
   `document.tables`, `document.sections` e conte as imagens em
   `part.related_parts`.
3. `.doc` legado: não abre com python-docx. Sem LibreOffice instalado, avise que a conversão exige essa dependência externa opcional.

Se um arquivo externo for recebido, trate-o como não confiável: descompacte com `zipfile` (nunca com ferramenta que restaura symlinks).

## Criar com python-docx — footguns

- **Nunca use `\n`** no texto: cada parágrafo é um `add_paragraph()`/`add_heading()` próprio.
- **Listas:** use os estilos prontos (`style="List Bullet"`, `style="List Number"`). Nunca insira `•` literal — renderiza em dobro se o estilo já tem marcador.
- **Títulos para o sumário:** use os estilos built-in (`Heading 1`, `Heading 2`…). Estilos customizados só aparecem no TOC se definirem nível de outline.
- **TOC (sumário):** python-docx não cria TOC nativo — insira um campo:
  ```python
  from docx.oxml.ns import qn
  from docx.oxml import OxmlElement
  p = document.add_paragraph()
  fld = OxmlElement("w:fldSimple")
  fld.set(qn("w:instr"), 'TOC \\o "1-3" \\h \\z \\u')
  p._p.append(fld)
  ```
  O Word só popula o sumário ao atualizar campos (pergunta ao abrir, ou atualize com o campo selecionado). Avise o usuário disso.
- **Rodapé com número de página:** mesmo caminho — campo `PAGE` via `w:fldSimple` dentro de um parágrafo de `section.footer.paragraphs[0]`. python-docx não tem "número de página" pronto.
- **Tabelas precisam de largura dupla:** `table.autofit = False` e defina `cell.width` em **cada célula**; as larguras das colunas devem somar a largura da tabela. Só mexer em colunas não basta.
- **Sombreamento de célula:** `w:shd` com `w:fill` no `tcPr` da célula — não confie em estilos automáticos.
- **Paisagem:** defina `section.orientation = WD_ORIENT.LANDSCAPE` **e troque manualmente** `page_width` ↔ `page_height` — o python-docx NÃO troca sozinho (diferente de outras libs).
- **Imagens:** `document.add_picture(caminho, width=Inches(6))` — sempre defina largura, senão a imagem entra no tamanho natural e estoura a página.
- **Estilos:** personalize via `document.styles["Heading 1"]` etc.; cada nível usado merece fonte, `space_before`/`space_after` e `keep_with_next` próprios.
- Linha horizontal: parágrafo com borda inferior — **nunca** uma tabela de uma célula.
- **Arquivo aberto no Word trava a escrita** (lock `~$`). Se PermissionError, avise para fechar o documento e tente outro nome.

## Editar um documento existente (leve)

- Para trocar texto use `run.text = "..."` em cada run. **Nunca** `text_frame.text = "..."` nem `paragraph.text = "..."`: isso apaga a formatação e colapsa o parágrafo num único run sem estilo.
- O Word fragmenta frases em vários runs (corretor, revisões): a frase visível pode não existir como string contígua. Percorra os runs do parágrafo e redistribua o texto entre eles em vez de procurar a frase inteira num run só.
- find-and-replace em massa: percorra parágrafos **e** células de tabela; tabela não é alcançada por `document.paragraphs`.

## Edição OOXML profunda

Quando o python-docx não expõe o que precisa (redlining/tracked changes, campo complexo, XML de cabeçalho):

```
1. zipfile.ZipFile(arquivo).extractall("unpacked")   # use pathlib/tempfile; arquivo externo = não confiável
2. edite unpacked/word/document.xml IN PLACE — sem reformatar ou "embelezar" o XML
3. rezipe TODOS os arquivos: zipfile em modo "w" passando por cada arquivo do unpacked,
   preservando [Content_Types].xml, as pastas _rels/ e a extensão .docx
   (no Windows, feche o zip antes de abrir; caminhos com pathlib)
```

- Preserve o `[Content_Types].xml` e os `_rels/` exatamente como estavam — rezipar sem eles corrompe o arquivo.
- Os alvos do XML são elementos `w:*` (ex.: `<w:t>`, `<w:r>`, `<w:pPr>`). Edite com cuidado cirúrgico; teste abrindo o resultado antes de declarar pronto.
- **Comentários:** um comentário OOXML exige seis arquivos entreligados (`comments.xml`, `commentsExtended.xml`, `commentsIds.xml`, `commentsExtensible.xml`, as relações e os content-type overrides) **e** os marcadores `<w:commentRangeStart>`/`<w:commentRangeEnd>`/`<w:commentReference>` no `word/document.xml` — até colocar os marcadores, o comentário existe mas fica invisível. Sem a necessidade real, evite criar comentários via OOXML cru; este é o ponto mais fácil de corromper.
- **Tracked changes:** envolva os runs em `<w:ins>`/`<w:del>` com `w:id`, `w:author`, `w:date`; dentro de `<w:del>` o texto é `<w:delText>`, não `<w:t>`. Marca de parágrafo apagada (`<w:del>` no `rPr` do `pPr`) significa "junte este parágrafo ao próximo".

## Verificar antes de encerrar

Não existe renderização automática no JINX (soffice/pdftoppm são externos opcionais). O gate é humano:

1. Reabra o arquivo com python-docx e confirme estrutura (nº de parágrafos, tabelas, títulos).
2. Se houver LibreOffice instalado e o usuário concordar, converta para PDF (ou use `pdf_forge` para inspecionar o PDF resultante) — sinalize que é opcional.
3. **Gate:** mostre o documento gerado ao usuário (caminho + resumo do conteúdo) e pergunte se está correto **antes de assumir que está pronto**. Não declare sucesso sem essa conferência.

## Não fazer

- Presumir pandoc/LibreOffice/Adobe — dependências externas opcionais.
- `\n` dentro de texto, `•` literal, tabela como régua horizontal.
- `paragraph.text = "..."` em documento existente (destrói formatação).
- Rezipar OOXML sem `[Content_Types].xml` e `_rels/`.
- Declarar "pronto" sem mostrar o resultado ao usuário.
