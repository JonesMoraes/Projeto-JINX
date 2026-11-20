---
name: pdf
description: >-
  Qualquer coisa com PDF: ler/extrair texto e tabelas, juntar (merge),
  dividir (split), girar, marca d'água, proteger com senha, criar PDF novo
  e OCR de PDF digitalizado. No JINX, a maior parte roda com as tools
  nativas pdf_forge (merge/split/extract/criar com capa; pypdf+reportlab)
  e file_processor (texto e tabelas via pdfplumber). Use quando o usuário
  mencionar ".pdf", "juntar pdfs", "dividir pdf", "extrair tabelas do pdf",
  "criar um pdf" ou similar.
version: 1.0.0
intents:
  - "juntar esses pdfs"
  - "dividir esse pdf"
  - "extrair as tabelas do pdf"
  - "criar um pdf"
  - "ler esse pdf"
  - "colocar marca d'água no pdf"
  - "proteger o pdf com senha"
params:
  type: object
  properties:
    action:
      type: string
      enum: [read, merge, split, create, edit]
      description: >-
        read: extrair texto/tabelas; merge: juntar PDFs; split: dividir por
        página; create: gerar PDF novo; edit: girar/marca d'água/senhas em
        PDF existente.
    paths:
      type: array
      items: {type: string}
      description: >-
        Caminhos dos PDFs de entrada. read ≥1, merge ≥2, split 1,
        edit ≥1, create ignora.
    out:
      type: string
      description: Pasta de saída (ou nome do arquivo único em merge/create).
    options:
      type: object
      description: >-
        Ajustes por ação: ex. {pages: "1-5,8"} no split;
        {rotate: 90}, {watermark: caminho}, {password: "..."} no edit;
        {title, layout} no create.
supported_os: [windows, any]
required_capabilities: [filesystem]
---

# Processamento de PDF

## Comece pelas tools nativas JINX

O JINX já cobre a maior parte sem código:

| Tarefa | Melhor ferramenta | Como |
|---|---|---|
| Ler texto e tabelas | Tool nativa **`file_processor`** | Aponte o caminho do PDF; devolve texto e tabelas via pdfplumber |
| Merge / split / extract | Tool nativa **`pdf_forge`** (actions/pdf_forge.py) | Merge, split, extração de páginas e criar PDF com capa (pypdf + reportlab) |
| Merge/split manual, girar, senha | `pypdf` | `PdfReader`/`PdfWriter` — snippets abaixo |
| Tabela → CSV/Excel | `pdfplumber` | `page.extract_tables()` → CSV por tabela |
| Criar PDF com layout | `reportlab` | Canvas (positionamento) ou Platypus (fluxo) |
| OCR de PDF escaneado | **Dependência EXTERNA opcional** | `pdftoppm` + `pytesseract` — pode não estar instalado; sem ele, informe o usuário |

Bibliotecas disponíveis no Python do app: `pypdf`, `pdfplumber`, `reportlab` (e `pandas` opcional para tabular). **Não existe pdf-lib (JS) nem qpdf/pdftk no JINX** — para linha de comando externa, trate como dependência opcional e não presuma.

## read — extrair texto e tabelas

1. Primeiro `file_processor` sobre o caminho — na maioria dos casos resolve.
2. Detalhado com pdfplumber:
   ```python
   import pdfplumber
   with pdfplumber.open(caminho) as pdf:
       for i, page in enumerate(pdf.pages, 1):
           texto = page.extract_text()
           for j, tabela in enumerate(page.extract_tables(), 1):
               ...  # tabela é lista de listas por linha
   ```
3. Tabela → CSV: escreva cada tabela com o módulo `csv` (ou `pandas.DataFrame(tabela[1:], columns=tabela[0]).to_excel(...)` se pandas estiver disponível), uma saída por tabela.
4. **PDF escaneado não tem texto:** se `extract_text()` volta vazio, o OCR é dependência externa opcional (`pdftoppm` para rasterizar + `pytesseract`); sem eles, diga ao usuário que o PDF é imagem e a leitura precisa dessa instalação.

## merge / split / edit com pypdf

```python
from pypdf import PdfReader, PdfWriter

# merge
writer = PdfWriter()
for arquivo in ["a.pdf", "b.pdf"]:
    for page in PdfReader(arquivo).pages:
        writer.add_page(page)
with open("merged.pdf", "wb") as f:
    writer.write(f)

# split (espelhe como pdf_forge faz: 1 página por arquivo)
reader = PdfReader("input.pdf")
for i, page in enumerate(reader.pages, 1):
    w = PdfWriter(); w.add_page(page)
    with open(f"pagina-{i:02d}.pdf", "wb") as f:
        w.write(f)

# girar 90° horário: page.rotate(90)
# marca d'água: page.merge_page(PdfReader("marca.pdf").pages[0])
# senha: writer.encrypt("user", "owner") antes de writer.write
```

Sempre escreva num arquivo **novo** e só depois renomeie/substitua o original — na prática, sobrescrever um PDF aberto num visualizador dá PermissionError no Windows.

## create com reportlab

```python
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet

doc = SimpleDocTemplate("relatorio.pdf", pagesize=letter)
styles = getSampleStyleSheet()
story = [
    Paragraph("Título do Relatório", styles["Title"]),
    Spacer(1, 12),
    Paragraph("Seu texto aqui.", styles["Normal"]),
    PageBreak(),
]
doc.build(story)
```

- **Nunca use caracteres Unicode de sub/sobrescrito** (₀…₉, ⁰…⁹) — as fontes embutidas os renderizam como quadradinho preto. Use a marcação XML do Paragraph: `H<sub>2</sub>O`, `x<super>2</super>`. Em texto desenhado no Canvas, ajuste fonte/posição manualmente.
- Acentos pt-BR funcionam nas fontes padrão; para outra fonte, registre o TTF antes de usá-la.
- Capa simples: `pdf_forge` já cria PDF com capa quando a tarefa é só encadear/montar.

## Gate antes de sobrescrever

Merge, split e edit gravam arquivos novos no diretório de saída. **Antes de escrever sobre um arquivo que já existe, pare e peça aprovação ao usuário**, listando os arquivos que seriam substituídos. Nunca sobrescreva o PDF de entrada: escreva numa pasta apartada (default: subpasta `pdf_saida/` ou a `out` do usuário).

## Não fazer

- Sobrescrever arquivos de entrada ou saídas existentes sem aprovação.
- Presumir pdf-lib, qpdf, pdftk, pdftoppm ou pytesseract — todos externos opcionais; o pipeline JINX é pypdf + pdfplumber + reportlab via pdf_forge/file_processor.
- Usar Unicode sub/sobrescrito no reportlab.
- Declarar leitura "completa" de PDF escaneado que só tem imagens, sem avisar que o OCR é opcional.
