---
name: xlsx
description: >-
  Cria, lê, edita e converte planilhas (.xlsx, .xlsm, .csv, .tsv): leitura
  via file_processor / openpyxl (data_only para valores), edição preservando
  formatos, criação com openpyxl (dados com header, largura de coluna
  manual), fórmulas que referenciam células de input (nunca valor inline) e
  validação por reabertura com openpyxl. Use quando o entregável primário
  é um arquivo de planilha: gerar planilha de dados, colunas calculadas,
  fórmulas, limpeza de dados, conversão entre formatos tabulares. NÃO use
  quando o entregável é Word, HTML ou script Python, mesmo com dados
  tabulares.
version: 1.0.0
intents:
  - "criar uma planilha"
  - "ler essa planilha"
  - "editar esse xlsx"
  - "converter csv em xlsx"
  - "converter a planilha em csv"
  - "montar uma planilha com fórmulas"
  - "limpar o csv"
params:
  type: object
  properties:
    action:
      type: string
      enum: [read, create, edit, convert]
      description: >-
        read: ler dados de planilha existente; create: nova planilha (exige
        sheet_plan); edit: alterar arquivo existente preservando formatos;
        convert: converter entre formatos tabulares (xlsx/csv/tsv).
    path:
      type: string
      description: >-
        Caminho do arquivo de entrada — obrigatório em read, edit e convert.
    out:
      type: string
      description: >-
        Pasta ou nome do arquivo de saída. Em convert, se a extensão de out
        (.xlsx/.csv/.tsv) indica o formato alvo; se ausente, o agente pergunta.
    sheet:
      type: string
      description: Nome da aba a operar (quando o arquivo tem várias).
    sheet_plan:
      type: string
      description: >-
        Outline da planilha para create: colunas, aba(s), fórmulas,
        formatação esperada e fonte dos dados.
supported_os: [windows, any]
required_capabilities: [filesystem]
---

# Planilhas (xlsx / csv)

| Tarefa | Ferramenta |
|---|---|
| **Ler** conteúdo rápido | Tool nativa **`file_processor`** (lê planilhas) |
| **Ler** modelo completo (fórmulas E valores) | duas passadas de `openpyxl` — veja abaixo |
| **Criar / editar** com fórmulas e formatação | `openpyxl` |
| **Dados em massa** (entrada/saída) | `pandas` (`read_excel`, `to_excel`) — opcional, mas disponível |
| **Converte** xlsx ↔ csv ↔ tsv | `pandas`/`openpyxl` + módulo `csv` |

No Python do app há `openpyxl` e `pandas`. **Não existe markitdown nem recalc via LibreOffice no JINX** — o recalc/LibreOffice é **dependência externa opcional**.

## Ler um arquivo

- Rápido: `file_processor` sobre o caminho — devolve o conteúdo por aba.
- **Ler modelo completo exige DUAS cargas de openpyxl:** o default devolve as fórmulas como strings sem valores; `load_workbook(data_only=True)` devolve os valores em cache sem as fórmulas. Uma passada só não dá as duas coisas.
- **`data_only=True` é destrutivo se salvar:** esse workbook não tem mais fórmulas — salvar substitui todas por literais permanentemente. Leia com `data_only` só para conferência, e salve a partir da carga default.
- **Arquivo que o próprio openpyxl escreveu lê `None` nas fórmulas com `data_only=True`**: sem mecanismo de recálculo no JINX, o valor em cache só passa a existir quando o Excel abrir o arquivo. Aviso isso ao usuário em vez de tratar como erro.
- `.xlsm` perde as macros sem `keep_vba=True` em `load_workbook`.

## Regras de qualidade do produto final

- **Fórmulas, nunca resultados hardcoded:** escreva `ws["B10"] = "=SUM(B2:B9)"`, não o total calculado em Python — a planilha precisa recalcular quando os inputs mudarem.
- **Fórmula referencia a célula do input, nunca valor inline:** todo número de entrada numa própria célula rotulada (`$B$6`), e a fórmula consulta (`=B5*(1+$B$6)`), nunca `=B5*1.05`. Assumptions em células próprias, citando a fonte quando existir.
- **Consistência por período/coluna:** a mesma fórmula em cada coluna do intervalo — célula editada solta no meio da linha é o erro silencioso mais comum.
- **Guarde os denominadores de zero:** `=SE(B2=0;"";A2/B2)` (ou `IFERROR(B2/C2; "")` com Excel em inglês — veja a nota de idioma abaixo) em vez de servir `#DIV/0!`.
- **Erro zero:** num arquivo novo não pode restar `#REF!`, `#NAME?`, `#DIV/0!`, `#VALUE!`.
- **Siga a spec do usuário literalmente:** nomes exatos de abas, cabeçalhos e a fórmula que ele determinou — redesign "melhorzinho" que calcula outra coisa é falha.
- **Editar arquivo existente = seguir as convenções dele** (elas vencem estas regras): localize primeiro as células de input designadas (fonte colorida, preenchimento) e escreva apenas nelas; não toque em fórmulas existentes.
- Workbook "para outra pessoa preencher" ganha legenda curta de quais células editar e uma linha de exemplo realista — nunca coloque essa linha num arquivo que você editou.
- **Formato numérico em toda fórmula nova** (`Cell.number_format`): porcentagem, moeda, data — nada infere sozinho; sem formato, 30% aparece como `0,3` e data como `45337`.

## Escolhendo fórmulas com verificação local

- Prefira funções da era **Excel-2007**: `SUMIFS`, `INDEX`, `MATCH`, `IFERROR`, `SUMPRODUCT`.
- **Nunca use `XLOOKUP`, `XMATCH`, `SORT`, `FILTER`, `UNIQUE`, `SEQUENCE`** — sem recalc local para validar, e a versão escrita por openpyxl não carrega metadados de spill; use `INDEX`/`MATCH` e faça ordenação/filtro/dedup em Python antes de escrever.
- Funções pós-2007 (`TEXTJOIN`, `IFS`, `SWITCH`, `MAXIFS`, `MINIFS`) precisam do prefixo `_xlfn.` na fórmula crua. Se não há certeza, troque pela combinatória 2007.
- O idioma do Excel do usuário determina os nomes (`IF_ERROR` vs `IFERROR`) e o separador (`;` vs `,`) — se ele reportar erro de fórmula, ajuste a esse dialeto.

## Criar com openpyxl

```python
from openpyxl import Workbook
from openpyxl.styles import Font

wb = Workbook()
ws = wb.active
ws.title = "Dados"
ws.append(["Mes", "Receita", "Custo", "Margem"])   # dados com header — sempre
for linha in registros:
    ws.append(linha)
n = len(registros)
for linha in range(2, n + 2):
    ws.cell(linha, 4).value = f'=IF(C{linha}=0,"",(B{linha}-C{linha})/C{linha})'
    ws.cell(linha, 4).number_format = "0.0%"
# largura de coluna manual (não existe autofit de verdade):
for col in ("A", "B", "C", "D"):
    maior = max(len(str(ws[f"{col}{i}"].value or "")) for i in range(1, n + 2))
    ws.column_dimensions[col].width = max(10, maior + 2)
wb.save("saida.xlsx")
```

- **Autofit é manual** — percorra o conteúdo e defina `ws.column_dimensions[letra].width`.
- Fonte profissional (Arial etc.) por estilo/célula, salvo pedido contrário.
- Merged cells: escreva **só no âncora** (topo-esquerda); o resto do range é `MergedCell` de leitura proibida.
- Gráfico: `chart.roundedCorners = False`, `overlay = False` na legenda e nos títulos, e em gráfico com eixos `x_axis.delete = y_axis.delete = False` — senão o Excel pode desenhar legenda por cima do plot.

## Editar preservando formatos

1. **Não salve por cima do original na primeira alteração** — grave em novo arquivo (ou cópia de segurança) e confirme antes de substituir; arquivo aberto no Excel dá PermissionError no Windows (lock `~$`).
2. `data_only=True` nunca no caminho que salva (troca fórmulas por literais).
3. `Cell.value =` preserva o formato da célula; é o caminho padrão. Um whois do número de formato: confira `number_format` se mudar a natureza do dado.
4. **Salvar um upload derruba caixas de texto, shapes e slicers.** Antes, procure `<xdr:sp ` em `xl/drawings/` e a pasta `xl/slicers/` dentro do zip (aberto com `zipfile`) — se houver, avise o usuário ou edite o XML da sheet direto.
5. Cabeçalho duplicado/vazio ou number format com aspas malfeita o openpyxl grava como está — e o Excel pode pedir "reparo". Corrija a fonte, não o sintoma.
6. Fórmula nova reescrita no XML da sheet: apague o `<v>` (valor em cache) da fórmula alterada, senão o Excel mostra valor velho.

## Converter xlsx ↔ csv ↔ tsv

```python
import pandas as pd
df = pd.read_excel("entrada.xlsx", sheet_name=0)
df.to_csv("saida.csv", index=False, encoding="utf-8-sig", sep=",")  # utf-8-sig: Excel abre acento direito
df.to_csv("saida.tsv", index=False, sep="\t")
df.to_excel("saida.xlsx", index=False)
```

- Converter **perde formatação, fórmulas (vira valor) e múltiplas abas** — escolha/nomeie a aba (`sheet`) e avise o que fica de fora.
- CSV não guarda tipo: datas viram texto e zero à esquerda some. Se precisar do tipo, o entregável é xlsx.
- Para CSV problemático (linha torta, cabeçalho deslocado), limpe com o módulo `csv` ou `pandas` antes de escrever o xlsx.

## Verificação sem LibreOffice (o caminho normal no JINX)

Recalcular com LibreOffice (recalc tipo upstream) é **dependência externa opcional** — o padrão no JINX é:

1. Reabra o arquivo salvo com openpyxl (carga default) e confira: fórmulas das células-chave como strings corretas (ranges, referências a células de input, guardas de divisão).
2. Valor conhecido: para cada fórmula, calcule em Python o resultado esperado e **diga ao usuário** o valor que deve aparecer; valor em cache só aparecerá quando o Excel abrir o arquivo.
3. Confira tipos de célula de input (texto vs número vs data — anos como texto `"2024"`, nunca `2024` com vírgula) e number_format das saídas.
4. **Gate:** mostre o resultado (caminho, abas, colunas, fórmulas principais, valores esperados) e pergunte se está correto antes de assumir pronto.

## Não fazer

- Valor calculado em Python gravado como literal no lugar de fórmula.
- Fórmula com número inline (`=B5*1.05`) ou sem guarda de divisão por zero.
- `data_only=True` no caminho que salva; salvar direto sobre o original.
- `XLOOKUP`/`SORT`/`FILTER`/`UNIQUE`/`SEQUENCE`.
- Converter sem avisar o que se perde (fórmulas, formatos, abas).
- Declarar "pronto" sem reabrir/verificar e sem mostrar o resultado ao usuário.
