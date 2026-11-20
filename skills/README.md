# Skills da JINX

Uma pasta por skill, sempre com `SKILL.md` (front matter YAML validado) e
`handler.py` (`class Handler(BaseSkill)` / `class Skill(BaseSkill)`). Hot
reload ativo: editar qualquer dos dois arquivos recarrega a skill sozinho.

Formato de referência: `skills/img-to-html/`.

| Skill | O que faz | Intents |
|---|---|---|
| `img-to-html` | Recria um mock de UI (imagem) como HTML + CSS + JS estáticos, em etapas com aprovação | "img to html", "recriar essa tela" |
| `ui-ux-pro-max` | Inteligência de design UI/UX: prioridades 1→10 (acessibilidade, toque, performance…), design system e guidelines por stack | "revise o design da interface", "crie o design system do projeto" |
| `design-taste` | Anti-slop frontend: regras de casa (uma seção por tela, bordas alinhadas, micro-animações discretas, fotos reais) e lista "never" | "refaça o site que parece genérico", "landing page profissional" |
| `web-artifact` | Mini-apps web complexos como HTML + CSS + JS estáticos (sem build), estado/rotas em vanilla | "criar um app web", "montar um mini-app" |
| `docx` | Documentos Word: ler (file_processor), criar/editar com python-docx, OOXML profundo via unpack → document.xml → rezip | "criar um documento word", "montar uma ata" |
| `pdf` | PDFs: ler/extrair, merge/split, criar (pdf_forge + pypdf/pdfplumber/reportlab), watermark, senhas | "juntar esses pdfs", "extrair as tabelas do pdf" |
| `pptx` | Apresentações: ler via file_processor, criar com python-pptx (footguns preservados), QA visual obrigatório | "criar um powerpoint", "montar um deck" |
| `xlsx` | Planilhas: ler/editar/criar/converter com openpyxl + pandas, fórmulas que referenciam inputs | "criar uma planilha", "editar esse xlsx" |
| `planning-with-files` | Trabalho de muitas etapas em arquivos persistentes (task_plan.md / findings.md / progress.md) | "planeja essa tarefa em arquivos", "organiza esse trabalho num plano" |
| `humanizer-texto` | Reescreve texto com cara de IA preservando todo o conteúdo (voz; texto escrito — na voz automática quem cuida é core/humanizer.py) | "humaniza esse texto", "tira o jeitão de ia desse texto" |

Regras que valem para todas: corpo em pt-BR; handler leve (só setup
determinístico e a instrução passo a passo — a tarefa criativa é do agente,
sempre com gates de aprovação); nenhuma dependência de node/npm.

Origem dos ports: `ui-ux-pro-max` (nextlevelbuilder), `docx`/`pdf`/`pptx`/
`xlsx`/`web-artifact` (anthropics/skills), `planning-with-files`
(OthmanAdi), `design-taste` (taste-skill 2.5, Leonxlnx), `humanizer-texto`
(humanizer 4.0, blader). Todos adaptados, não copiados.
