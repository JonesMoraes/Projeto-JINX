# Histórico de alterações

## 2026-11-14 — Google Agenda como agenda principal
- Painel e ferramenta agenda_sync usam Google Calendar por padrão. Campos
  de lista Trello substituídos por calendário Google, JSON OAuth e conexão no
  navegador. Sincronização explícita; CRUD/undo permanecem locais.
- Temporizador Trello da instalação desativado via config_manager; eventos,
  vínculos e credenciais anteriores preservados. Trello continua como ferramenta
  independente/opção legada explícita, sem fallback automático após falha Google.
- 417 testes passaram no Python 3.15.2. Nenhum evento/conta real acessado;
  arquivo OAuth e consentimento do usuário ainda necessários nesta instalação.

## 2026-11-14 — Política de Python estável atualizado
- Requisito do interpretador em .python-version/setup.py e referência em
  requirements.txt. Inicializador verifica python.org, valida hash/assinatura
  do instalador e testa dependências antes de selecionar o ambiente novo.
- Ambientes gerenciados ficam em .jinx_runtime; ambiente anterior preservado
  em caso de falha. Runtime opcional de gestos mantém seu Python 3.12 separado.
- Python 3.15.2 instalado/selecionado; 411 testes aprovados, pip check sem
  conflitos e startup real com conexão/microfone/recepção/reprodução iniciados.

## 2026-11-14 — Controle de mouse por pinça
- Controle local opt-in: indicador move, pinça sustentada segura, abertura solta.
  Arma somente após mão aberta; perda da mão e watchdog liberam o botão.
- Usa a webcam compartilhada; modelo MediaPipe roda em ambiente separado,
  sem alterar as dependências do aplicativo. Instalador apresenta tamanho e
  exige confirmação. F10/Esc e botão PARAR interrompem; não ativa no boot.
- 405 testes passaram com mouse/landmarks simulados. Instalação do runtime e
  teste físico da mão/câmera permanecem pendentes de aprovação/uso explícito.

## 2026-11-14 — Posição do botão de webcam
- Webcam movida para a mesma linha de microfone e interromper, com ícone
  compatível com os controles. Barra inferior removida; botão oculto em tela
  cheia, mantendo o atalho F9 e o indicador de captura ativa.

## 2026-11-14 — Botão de webcam contínua
- Barra inferior com LIGAR/DESLIGAR WEBCAM e atalho F9, visível também em
  tela cheia. O botão abre a imagem ao vivo e mantém a captura até desligar.
- Estado de abertura/cancelamento e liberação explícitos; captura única,
  primeiro frame confirmado, falhas de dispositivo informadas e handles liberados.
- Captura local pela implementação existente; sem gravação ou envio automático.
  Start/stop externos passam por sinais Qt; testes usam câmeras simuladas.
- Validação: 389 testes passaram; render Windows conferido com a webcam
  desligada. Captura física depende do teste do usuário pelo botão/F9.

## 2026-11-14 — Correção e integração da expansão
- Expansão da branch feature/expansion-2026-11-14 preparada para integração
  ao main local, preservando dados pessoais e credenciais.
- Atualizador: recuperação e confirmação de startup usam o mesmo marcador e
  diretório de backups da aplicação; testes cobrem os caminhos de produção.
- Autorreparo: após confirmação humana, baseline/candidato passam por import
  em cópia temporária de fontes e testes específicos disponíveis antes da
  troca; falha, timeout ou edição concorrente preservam o arquivo original.
  Subprocesso não é sandbox. Snapshot não copia config, assets ou dados pessoais.
- HUD: teste usa HTML temporário; falhas de página, renderer ou WebGL voltam
  ao rosto nativo sem sobrescrever a preferência. Renderização real de assets
  EVO/ECHO ainda requer validação na máquina; não houve adaptação dos assets.
- Comentários inválidos do sketch Arduino corrigidos para //; estabilidade
  dos testes Windows melhorada para caminhos curtos e encoding.
- Escopo parcial e validações externas descritos em docs/historico/INTEGRACAO_EXPANSAO.md.

## 2026-11-14 — Esferas EVO/ECHO e prévia de vozes
- Removido o opt-in global que havia ocultado as esferas na execução normal
  pelo Windows. Restrição mantida apenas em executor restrito, testes sem
  tela ou desativação explícita. Views continuam criadas apenas ao selecionar.
- Menu de visual mostra as quatro escolhas e explica indisponibilidade.
  Fullscreen preserva EVO/ECHO; mudança de esfera persiste ao sair dele.
- Cada voz tem botão de prévia, sem aplicar/salvar. Síntese via core.gemini,
  contas e deadlines centralizados; saída PCM na rota validada do aplicativo.
  Parar/fechar cancela amostras tardias; fila mantém só o pedido mais recente.
  Cache em RAM limitado a oito amostras. Microfone e fala Live pausam durante
  reprodução, com restauração mesmo após falha ao fechar a saída.
- 288 testes selecionados aprovados (incluindo testes Qt e respostas Gemini
  simuladas). Reprodução online das prévias e renderização Chromium ainda
  precisam ser conferidas na abertura normal; executor mantém WinError 10013.

## 2026-11-14 — Roteamento de áudio e abertura sempre em tela cheia
- “Padrão do sistema” e nomes salvos resolvem para IDs físicos validados.
  Falta de dispositivo não retorna mais None silenciosamente. Fallback após
  falha exclui a rota que falhou e exige transporte confirmado na alternativa.
- Removidos aliases portugueses/ingleses do seletor; probes por dispositivo,
  direção e taxa; cache invalidado ao mudar taxas e enumeração concorrente
  serializada. Cache/picker aquecidos antes da conexão de voz, fora do Qt.
- Probes incluem drenagem da saída e fecham streams mesmo após erro. Saída
  serializa escrita/fechamento para impedir close durante write em worker.
  Teste de tom usa o mesmo contrato RawOutputStream/24 kHz/mono/int16 do app.
- Pico de entrada sem overflow int16, sem afirmar transcrição por amplitude.
  Volume nomeado verifica leitura e desmuta quando o usuário aumenta o nível.
- F8 abre os testes; evita testes simultâneos no mesmo painel. Encerramento
  por voz fecha pelo sinal Qt e solicita saída do loop/liberação de streams.
- JinxUI inicia sempre em fullscreen/orb; F11 continua restaurando a janela.
- 279 testes selecionados passaram. Fluxo de saída detectado em loopback;
  frase sintetizada localmente ouvida claramente pelo usuário. Conversa online
  e suíte completa seguem não aprovadas no executor com WinError 10013.

## 2026-11-14 — Tela cheia com orb e pop-ups compactos
- F11 agora oculta painéis e mostra somente o orb nativo, centralizado, sem
  labels/waveform. Restaura estilo, painéis, tamanhos e janela maximizada.
- Avisos de 268×76, até três visíveis, abrem detalhes apenas por clique,
  atalho ou comando; sete segundos e histórico de 24 entradas com conteúdo.
- Pop-up flutuante recolhível/ampliável; conteúdo anterior preservado,
  quiz com respostas mantidas e mídias na própria janela do aplicativo.
- Plugin display_control, comandos PT/EN, Ctrl+O e Ctrl+Espaço. Emissão de
  sinal pelo JinxUI e confirmação de processamento no Qt para tools workers.
- Confirmações humanas/expiração preservadas; câmera ativa e parar gravação
  continuam acessíveis. Sem novo QApplication, dependência ou asset externo.
- 17 testes novos passaram; regressão selecionada: 261 testes em 23 módulos.
  F11, abrir resultado, Esc e orb isolado verificados na janela real.
  Voz física continua dependente da conexão bloqueada no executor.

## 2026-11-14 — Correções de inicialização do HUD e diagnóstico de voz
- HUD nativo por padrão; WebEngine não é mais importado/criado ocultamente
  para rosto/núcleo. Views web opcionais são criadas só quando selecionadas.
  Se indisponíveis, visual salvo recua para rosto sem sobrescrever config.
  Botão HUD mostra o estilo realmente exibido e alterna só entre disponíveis.
- core/voice_runtime.py verifica conexão local com prazo e validação de pares
  antes de entrar no asyncio. Recusa/timeout aparece no painel e estado ERRO;
  falhas de inicialização não encerram silenciosamente o worker de voz.
- Comandos digitados também mostram o motivo quando a voz não pôde iniciar.
  Sem troca de event loop, monkeypatch de sockets ou alteração de permissões.
- INICIAR_JINX.cmd usa o ambiente local e preserva stdout/stderr em logs.
- 244 testes selecionados passaram, incluindo 11 novos. Aplicativo reaberto
  normalmente, sem flags de WebEngine, com diagnóstico WinError 10013 observado
  no HUD. Voz real e suíte completa seguem bloqueadas neste executor.

## 2026-11-14 — Retomada: interrupção por voz, navegador e preferências
- 5.1: detector opt-in integrado ao microfone; início da fala preservado,
  cancelamento no loop de voz e descarte de áudio antigo no pipeline.
  Corrigida análise espectral de blocos mono (frames, 1) do sounddevice.
- 5.2: perfil persistente exclusivo JINX para automação; ação snapshot
  acessível e texto com fronteira untrusted; cancelamento de timeout e logs.
- 6.1: propostas de preferências com revisão/aceite local, arquivo separado,
  escrita atômica, listagem/rejeição/remoção e undo.
- 233 testes selecionados passaram. Smoke Qt dos plugins sem warnings.
  Suíte completa/voz física não aprovadas: diagnóstico mínimo de asyncio
  bloqueado no Windows, registrado pelo preflight dos testes internos.
- Nenhuma dependência instalada, conta conectada, commit ou push nesta etapa.

## 2026-11-13 — Fase 3 e parada antes da Fase 4
- Documentos PPTX/DOCX/XLSX e PDF com arquivos verificados e undo; dependências
  opcionais sob demanda na UI, sem aumentar requirements padrão.
- Legendas YouTube pela API atual e resumo no painel; reprodução preservada.
- Reuniões mic/loopback com início/parada explícitos, indicador persistente,
  STT configurado e resumo/itens via ladder. Sem download automático de modelos.
- Pesquisa de voos pelos modos web existentes, fontes no painel e status honesto.
- 187 testes passaram, HUD/cartões/indicador e pipeline sintético PT-BR/EN
  verificados. HTTP/CoinGecko reais passaram; YouTube exemplo indisponível.
- pypdf (0,40 MB) e SoundCard (0,04 MB) instalados opcionalmente. LibreOffice
  ausente: conversão requer instalação posterior ou Exportar PDF no Office.
- Fase 4 não iniciada por solicitação do usuário; envio GitHub autorizado.
  Limites de validação registrados em docs/historico/PHASE_3_VALIDATION.md.

## 2026-11-13 — Tarefas 2.3–2.6
- Brilho por monitor WMI com readback/undo; captura real de lista verificada.
- Contexto de janela opt-in sem screenshots, com limite untrusted e envio não final.
- Watchers opt-in de cripto, HTTP e RAM; jogos Steam/Epic/Riot por manifests locais.
- 160 testes passaram. Jogos detectáveis nesta máquina: lista vazia; nenhum jogo lançado.
- Testes de efeitos de brilho/alertas/launch simulados. Não representam escuta real
  PT-BR/EN. Detalhes, arquivos e comandos em docs/historico/EXPANSION_PROGRESS.md.

## 2026-11-13 — Tarefa 2.2

- Plugin de bateria: carga, tomada e autonomia estimada; consulta WMI Windows
  sob demanda para capacidade/desgaste, com limite de 4 s e sem pacote novo.
- Alertas opt-in por voz e cartão de configurações, limites 20/80% por padrão,
  reversão via undo existente. Não altera hardware nem políticas de energia.
- Monitor a cada 30 s nos modos Live/pipeline; silêncio, mute, repouso,
  conversa recente, histerese e cooldown; falha no envio não consome o alerta.
- 141 testes passaram (16 novos). Consulta real detectou 30% e tomada;
  capacidade de projeto não disponível no driver, saúde `unverified`.
  Descoberta do plugin/cartão e consulta pelo dispatcher verificadas.
- Voz PT-BR/EN e escuta real de alertas pendentes após reinício do app.

## 2026-11-13 — Tarefa 2.1

- Nova ação process_manager: consulta de CPU/RAM por processo, nome exato ou PID,
  com tabela no painel. CPU amostrada por 250 ms e normalizada à capacidade total;
  RAM RSS pode incluir memória compartilhada.
- Fechamento exige confirmação da interface; no Windows envia WM_CLOSE sem
  fallback para término forçado. Force exige tentativa anterior e nova confirmação.
- Protege JINX, seus executáveis e processos críticos; revalida identidade após
  aprovação para impedir atingir outro processo que reutilizou o PID.
- 125 testes passaram (15 novos); consultas reais de CPU/RAM e descoberta das
  20 ações passaram. Encerramentos testados somente com processos simulados.
- Sem dependências novas, contas ou alteração dos módulos centrais de segurança.
  Teste por voz do novo recurso depende de reiniciar o app.

## 2026-11-13 — Validação integrada de voz

- Usuário confirmou os quatro comandos no app atualizado: consulta de memória,
  início/fim do foco e pergunta de horário em inglês.
- Regressão PT-BR/EN e controle do foco aceitos. Permanecem pendentes as
  integrações que exigem credenciais próprias e síntese/escuta reais do Edge.
- Nenhum código, dependência ou configuração de conta alterado neste registro.

## 2026-11-13 — Tarefa 1.8

- Provedor Edge TTS opcional no seletor de voz, padrão PT-BR Antonio,
  opções PT-BR/EN e consulta atualizada de vozes. Sem conta/chave prévia.
- TESTAR verifica lista/voz; OUVIR TESTE sintetiza uma frase e envia PCM
  mono 24 kHz à saída escolhida. Confirmação de escuta ainda depende do usuário.
- edge-tts e miniaudio ausentes nesta máquina; importação sob demanda e
  instalação apenas pelo botão do painel, com plano/tamanho/hashes verificados
  e recusa acima de 20 MB. requirements.txt não alterado.
- 110 testes passaram; smoke Qt do painel passou sem reproduzir/instalar.
  Síntese online e escuta reais pendentes das dependências opcionais.
- Implementações da Fase 1 disponíveis na branch; validação integrada real
  ainda pendente, portanto a fase não foi declarada concluída nem mesclada.

## 2026-11-13 — Tarefa 1.7

- Groq STT dedicado no seletor de audição, dois modelos multilíngues,
  idioma automático/pt/en e chave vazia para cadastro manual.
- Preservada configuração antiga whisper@groq; nenhuma seleção ou chave
  do usuário alterada automaticamente e nenhum modelo local instalado.
- TESTAR verifica conexão/modelo; GRAVAR 4 S E TESTAR registra áudio
  explicitamente e mostra transcrição. Captura cancela ao ocultar o painel
  antes do envio; requisição já enviada não pode ser desfeita.
- Trabalho de rede/captura fora da thread Qt; resultado por sinal, texto
  da transcrição exibido como texto simples. Sem SDK ou dependências novas.
- 98 testes passaram e smoke do sinal Qt verificado. Teste real com chave,
  gravação e conversa PT-BR/EN continua pendente.

## 2026-11-13 — Tarefa 1.6

- Três plugins: foco, humor e frases ignoradas, configuráveis em ⚙ e por voz;
  persistência via config_manager e desfazer via API existente.
- Foco mostra agenda, orienta respostas concisas, suprime check-ins de
  ociosidade e permite lembrete de água opcional (respeita quiet hours).
- Humor leve, desligado por padrão, com prioridade do foco e sem alterar
  confirmação/segurança. Motor local atualiza estilo a cada geração.
- Frases inteiras normalizadas são descartadas em texto/STT local antes do
  modelo. No áudio nativo Gemini Live o comportamento é orientativo, sem
  garantia de bloquear ações ou impedir transmissão do áudio.
- Playlist do usuário opcional abre no navegador; reprodução não verificada
  e pausa manual. Não há playlist/servidor/conta de origem configurados.
- 87 testes passaram; voz real e reprodução musical não verificadas.
  Nenhuma dependência nova ou alteração em módulos de segurança protegidos.

## 2026-11-13 — Tarefa 1.5

- Divergência do backlog confirmada com o usuário: o plugin de origem é de
  vendas/marketing. Usuário solicitou os dois recursos, separados.
- Rastracking de vendas/clientes/suporte: servidor HTTPS e chave vazios,
  agregados Decimal, paginação por cursor com limites, mensagens de suporte
  ocultas salvo solicitação explícita. Contrato real depende da API do usuário.
- Encomendas: plugin separado para Correios com token manual, leitura de
  eventos/status/data e alternativa de consulta manual no site oficial.
  API restrita ao contrato do remetente; outras transportadoras não integradas.
- 71 testes passaram, incluindo regressões; sintaxe e descoberta verificadas.
  Contas reais e voz ainda não verificadas. Nenhuma dependência nova.

## 2026-11-13 — Tarefa 1.4

- Plugin Cakto para vendas brutas pagas de hoje/mês, pedidos recentes,
  consulta de pedido por ID e produtos; campos de conta vazios na interface.
- API oficial, somente leitura de negócio; autenticação OAuth2 por token em
  memória com cache por credencial, renovação e proteção contra redirects.
- Cálculos Decimal, BRL/USD separados e filtro por pagamento; limites de
  páginas/tempo, duplicatas e dados inconsistentes produzem resultado parcial.
- Consultas longas rodam em segundo plano e entregam resultado no painel/voz.
- 55 testes passaram, incluindo regressões. Sem dependências novas.
- Conta real e comandos falados continuam não verificados até configuração
  manual e reinício do app para carregar o plugin.

## 2026-11-13 — Tarefa 1.3

- Organizador local de tarefas: criar, listar, alterar título/prazo/prioridade/
  nota, concluir, reabrir e arquivar; filtros e consulta combinada com eventos.
- Eventos usam a agenda existente; edição e arquivamento por ID evitam
  ambiguidades; desfazer e restauração de cartão Trello testados com mocks.
- Painel em tabela, seleção de item, filtros e controles de tarefas/eventos.
- 38 testes passaram; smoke headless confirmou criação, seleção, conclusão e
  filtro no painel. Voz do novo plugin ainda não verificada; precisa reiniciar.
- Sem dependências novas e sem conta obrigatória; dados pessoais ignorados
  pelo Git. Nenhuma alteração em confirm.py, undo.py ou sandbox.

## 2026-11-13 — Tarefa 1.2 (integração real pendente)

- Plugins Trello e agenda: quadros/listas/cartões, criação, movimentação,
  conclusão e arquivamento com readback; undo para alterações reversíveis.
- Store mínimo de eventos e sync bidirecional com lista escolhida pelo usuário;
  painel em ⚙; reagendamento por título; persistência atômica e conflitos visíveis.
- Sync OFF por padrão, nenhum login/destino de origem importado; troca de
  conta/lista bloqueia vínculos antigos, timeout de criação não duplica cartões.
- Testes simulados e smoke headless do painel; conta Trello real e voz ainda
  unverified. Nenhuma dependência nova; nenhum módulo de segurança alterado.

## 2026-11-13 — Tarefa 1.1

- Rotação primary-first de até três chaves integrada à ladder e reconexão Live.
- Cooldown por fingerprint da chave, configurável por campos de senha no plugin;
  mudanças de configuração sem reiniciar. Sem dependências novas.
- Testes offline verificam 429 A→B, cooldown, credencial externa isolada,
  atualização de configuração, Live e fallback de provedor. Teste real com
  contas secundárias ainda depende de o usuário cadastrá-las.
- Atribuição do port em NOTICE.md. Módulos de segurança não alterados.

## 2026-11-13 — Fase 0 concluída

- Auditoria estática e mapeamento completo em assets/extras/IMPLEMENTATION_PLAN.md.
- Baseline de inicialização, conexão de áudio e consulta local registrado em docs/historico/BASELINE.md; teste falado PT-BR/EN confirmado pelo usuário.
- Git local e branch feature/expansion preparados; exclusão de assets Brahma, arquivos locais e dados pessoais do versionamento.
- Nenhuma funcionalidade nova, alteração de segurança ou dependência instalada nesta fase.


## 2026-11-15 — Fase 6, continuação local

- Propostas automáticas conservadoras de memória factual PT-BR/EN; painel de
  aprovação/rejeição, deduplicação, conflito e desfazer; gravação JSON atômica.
- Dev agent: pasta aprovada resolvida, recusa de caminhos absolutos gerados,
  preservação de edições intermediárias e posteriores no undo; validação
  indisponível não é sucesso.
- Autorreparo: descartar proposta e recusar candidato sem mudanças.
- Skill Forge: recusar blocos de código; rascunho continua sem registro/execução.
- Testes e limites em docs/PHASE_6_LOCAL_CONTINUATION.md.

## 2026-11-15 — Login Google guiado

- Entrar com Google no navegador na Agenda e Integrações; preparação local com importação de JSON ou ID/segredo OAuth Desktop quando faltar configuração, preservando tokens e serviços selecionados.
- Sete testes novos de preparação, cancelamento, validação e preservação local. OAuth real depende do registro e consentimento do usuário.

## 2026-11-15 — Correção de permissões Google incompatíveis

- Separar consentimento e credenciais de YouTube e Gmail/Agenda/Drive, evitando o erro 400 por combinar drive.file com YouTube.
- Renovação e verificação de conta usam a credencial de cada grupo; login incompleto preserva tokens anteriores antes da gravação. Seis testes novos.

## 2026-11-15 — Configurações compactas e chaves de ativação

- Botões de ação menores, alinhados à esquerda; navegação, campos e títulos mais compactos.
- Chaves nativas acessíveis por mouse/teclado, com Ligado/Desligado, em integrações,
  plugins, automação, inicialização e sincronização manual da agenda.
- Automação separa ações de ativações; as chaves acompanham o estado real sem
  executar callbacks durante atualizações. Credenciais e IDs avançados recolhidos.
- Preservados callbacks existentes, permissões, armazenamento e temas. Nas
  integrações, mudanças continuam sendo aplicadas por Salvar ou pela ação de conexão.
- 44 módulos da suíte interna aprovados, sem falhas/timeouts; cinco testes novos
  de interação, persistência e sincronização. Renderização Qt conferida em fixtures.
