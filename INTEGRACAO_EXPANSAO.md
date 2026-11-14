# Integração da expansão — 14/11/2026

Origem: feature/expansion-2026-11-14, commit 5bfef86. A versão main anterior
era 9a40f6d. Usuário autorizou corrigir e incorporar após revisão do projeto.
Os registros de timeouts e ausência de push nos relatórios anteriores são
históricos; não descrevem a situação desta integração.

## Correções

- Atualização: marcador e backups compartilhados em .jinx_update. Confirmar
  startup remove o marcador real; falha permite recuperação no boot seguinte.
  Testes conferem os defaults de produção, a restauração e o descarte do marcador.
- Autorreparo: após confirmação no HUD e antes de modificar o original,
  importa baseline e candidato em processos separados, numa cópia temporária
  contendo somente fontes Python. Executa test_<nome_do_modulo>.py se existir.
  Erro, timeout, baseline quebrada ou edição durante a validação impedem a
  instalação. Não há instalação de dependências nem cópia de credenciais.
  Processos usam -I e -B para evitar importar bytecode antigo do baseline.
  Isso não é uma sandbox: a revisão autoriza executar Python com as permissões
  do usuário. Import e testes disponíveis não provam todos os comportamentos;
  funções sem teste dedicado recebem apenas a verificação de importação.
  Arquivos que já não importam devem seguir o fluxo de desenvolvimento manual.
- HUD: teste de carregamento fornece seu próprio HTML temporário; teste de
  ausência de assets não acessa rede. Falhas notificadas pela página, processo
  renderer ou ausência de WebGL retornam ao rosto nativo naquela sessão,
  registrando o motivo sem mudar a preferência salva. Isto não comprova nem
  corrige todos os possíveis defeitos internos do visual EVO/ECHO.
- Arduino: comentários usam //; o teste rejeita diretivas # desconhecidas.
  Não houve compilação com Arduino CLI nem gravação de firmware.
- Testes Windows: fixtures com paths normalizados e stdout UTF-8 no runner;
  log inicial de execução de projeto não depende de emoji suportado pelo terminal.

## Escopo que continua parcial

| Item do plano | Entrega incorporada | Ainda não entregue ou validado |
|---|---|---|
| Google, Spotify, Discord, casa, Instagram e upload | Clientes/plugins, configurações e testes simulados | Consentimento, contas e efeitos reais; Discord não executa ferramentas remotas nem responde; Instagram não publica/envia. |
| Imagens, áudio e interrupção | Geração Gemini configurável, prévia de voz, roteamento e barge-in | Geração real, WebEngine e latência física na versão integrada. |
| Memória e skills | Preferências explícitas revisadas e rascunho inerte de skill | Não há aceitação automática, execução isolada de skills ou heurística completa de propostas de memória. |
| Presença e fitness | Processamento local e opt-in; MediaPipe opcional | Câmera/pose reais e dependências opcionais conforme configuração do usuário. |
| Circuitos | Guia textual DHT11/Pro Mini e sketch corrigido | Painel esquemático/pinouts do plano e compilação no toolchain Arduino. |
| Radar | Consulta pública e mapa Qt | Globo 3D/rotas e validação dos dados reais. |
| Android | PWA, logout e revogação | APK/Kotlin, integrações nativas e teste em Android real. |
| Atualizações | Digest, staging, confirmação, aplicação e rollback corrigido | Build/release automatizado e ensaio de atualização com release real. |

Esses itens não são apresentados como implementação integral das Fases 4–8.
Nenhuma conta, publicação, câmera, pacote pesado ou atualização real é ativada
para validar a integração. Confirm/undo e regras centrais de segurança não
foram alterados pelas correções.

## Verificação

Comando: `.venv\Scripts\python.exe -m unittest discover -s tests -v`, com
Qt offscreen e saída UTF-8. Resultado final: **384 testes passaram**, sem
falhas ou skips, em 18,13 s no Python 3.12.10 instalado. Evidência local:
logs/expansion-fix-tests-20261114.log. Testes focados verificaram
rollback, runtime inválido, regressão funcional, timeout, edição concorrente
e ausência de credenciais na cópia de validação.
