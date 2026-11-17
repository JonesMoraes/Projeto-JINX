# P1 — ferramentas locais e conectores

Esta fase amplia as ferramentas locais do JINX sem enviar alterações ao GitHub.
As ferramentas aparecem no registro automático de `actions/` e o cliente MCP em
`plugins/`; ações mutáveis usam o mecanismo de desfazer quando isso é possível.

## O que está disponível

- **Arquivos:** `fs_total` lista, lê, cria, grava, anexa, copia, move/renomeia,
  consulta metadados e altera permissões por caminho completo. Exclusões de
  arquivos regulares (até 16 MiB) vão para `memory/fs_trash`; diretórios não são
  removidos recursivamente. `search_scale` pesquisa conteúdo e nomes em várias
  pastas, e `edit_block` substitui trechos exatos com verificação de contagem e
  desfazer protegido por hash.
- **Shell persistente:** `shell_persistent` mantém sessões PowerShell, bash ou
  zsh, com diretório e variáveis persistentes, limites de saída e timeout.
- **REPL:** `repl_polyglot` mantém sessões Python e JavaScript/Node separadas,
  conserva variáveis entre avaliações e encerra o worker se o código exceder o
  timeout. A execução ocorre em subprocesso com as permissões do usuário; não é
  um sandbox. Node.js é opcional e precisa estar instalado no sistema.
- **SSH/SFTP:** `ssh_ops` valida a chave do servidor contra `known_hosts` e recusa
  hosts desconhecidos, executa comandos e transfere arquivos. A senha, se usada,
  vem de uma variável de ambiente; também aceita arquivo de chave. Não há
  credencial salva pelo JINX e a conexão remota não foi executada nesta validação.
- **Processos:** `process_manager` ajusta prioridade e afinidade de CPU quando o
  sistema oferece suporte; alterações podem ser desfeitas. No Windows, as classes
  são Idle/Below normal/Normal/Above normal/High; em POSIX não se tenta elevar
  prioridade acima do permitido pelo usuário.
- **Documentos e mídia:** `docs_native` lê documentos Office e edita cópias de
  planilhas XLSX; `pdf_forge` cria, junta, divide, adiciona capa e extrai texto de
  PDFs; `media_convert` converte imagens com Pillow e áudio/vídeo com FFmpeg.
  O FFmpeg do sistema é preferido; `imageio-ffmpeg` fornece um binário local como
  alternativa.
- **MCP:** em ⚙ → Configurações dos plugins → Cliente MCP, o usuário pode ativar
  um servidor stdio local ou um endpoint HTTP local/HTTPS. O plugin lista e chama
  ferramentas, lista/lê recursos e lista/obtém prompts MCP. Servidores remotos em
  HTTP sem TLS são recusados. Credenciais HTTP são lidas apenas de uma variável de
  ambiente cujo nome é configurado na interface; o valor do token não é salvo em
  `api_keys.json`. O usuário deve confiar no executável/servidor que configurar.

## Dependências

As dependências necessárias estão em `requirements.txt`: SDK oficial `mcp`,
`pypdf`, `reportlab`, `imageio-ffmpeg` e `paramiko`, além de Pillow/openpyxl já
usados pelo projeto. `ocrmypdf` permanece opcional e requer instalação externa
para OCR de PDFs digitalizados. A suíte não afirma que serviços remotos ou
credenciais do usuário estão configurados.

## Limites operacionais

- Conversão/renderização de vídeo grande ou 4K pode consumir bastante CPU, RAM e
  espaço temporário; 1080p é o padrão recomendado para máquinas com 16 GB de RAM.
- Prioridade/afinidade depende das permissões e capacidades do sistema.
- Operações MCP executam chamadas no servidor escolhido pelo usuário. Saídas são
  marcadas como conteúdo externo não confiável; isso não substitui isolamento do
  processo stdio configurado.
- A conexão MCP stdio foi validada contra um servidor-fixture local; HTTP remoto
  depende de endpoint e credenciais reais e não foi testado nesta rodada.

## Validação

Testes focados: `test_mcp_client`, `test_media_convert`, `test_pdf_forge`,
`test_fs_total`, `test_process_controls`, `test_repl_polyglot` e `test_ssh_ops`.
A suíte completa é executada por:

```powershell
.jinx_runtime\envs\3.14.10\Scripts\python.exe tests\run_internal_checks.py
```

Ruff pode ser executado com `python -m ruff check .` no ambiente que o contém.
