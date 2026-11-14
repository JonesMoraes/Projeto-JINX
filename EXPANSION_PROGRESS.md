# Execução local — expansão JINX

Histórico inicial da retomada (14/11/2026): o registro abaixo começou após
5.1, 5.2 e 6.1. O estado atualizado das implementações 6.2–8.3 e suas
pendências de validação está na última seção deste arquivo. Validações reais
de contas/serviços continuam separadas dos testes locais.

Registro histórico da parada anterior antes da Fase 4:
PHASE_3_VALIDATION.md. Ajustes de integração: protocolo Epic com pontos,
catálogo Groq legado, indicador de gravação em toolbar e tamanho/hash de
dependências opcionais. Suíte final: 187 testes passaram.

## Correção de áudio e fullscreen padrão — 14/11/2026

Atualização: EVO/ECHO voltaram à seleção normal pelo Windows. O bloqueio
global por opt-in foi substituído por detecção do executor restrito; o visual
escolhido é preservado no fullscreen. Vozes têm prévia por opção, cancelável,
sem alterar a voz ativa antes de Aplicar. 288 testes selecionados aprovados;
amostras online e WebEngine real ainda exigem validação fora do executor.

- Problema encontrado: resolve('', kind) retornava None sem usar a API
  validada pelo seletor. Resolução de nomes também aceitava _usable() sem
  verificar transporte. Aliases em português entravam como dispositivos reais;
  cache por API não distinguia endpoints e preservava probes de taxas antigas.
- core/audio_devices.py agora resolve nomes/defaults por endpoint físico,
  respeita o default físico do SO, testa transporte por dispositivo/direção/
  taxa e exclui endpoints que falharam no fallback. Se não há rota validada,
  informa indisponibilidade, em vez de abrir um None não verificado.
- Enumeração concorrente única e prefetch independente da rede. Configure com
  taxas inalteradas preserva cache quente; mudança de taxas/refresh limpa
  probes. Aliases PT/EN filtrados. Recursos fechados mesmo se stop falhar.
- main.py resolve endpoints fora do loop via to_thread; microfone confirma
  start antes de aceitar abertura. Saída usa SerializedOutput para aguardar
  a escrita em curso antes de fechar a stream. Encerramento por voz passa
  pelo sinal Qt, e finish solicita saída do loop com tempo limitado de espera.
- F8 abre AUDIO DEVICES; testes de entrada/saída não se sobrepõem. Teste de
  tom usa RawOutputStream igual ao fluxo do app, com rampa nas extremidades.
  Pico de entrada usa int32 para evitar overflow de -32768. Detecção de sinal
  não é mais descrita como prova de reconhecimento claro de fala.
- Aumento de volume em dispositivo nomeado desmuta e verifica leitura real.
  Não houve ajuste automático do volume geral durante os testes desta tarefa.
- ui.py agora abre sempre com showFullScreen(), já no modo orb. Não depende
  de parâmetro de terminal, edição de api_keys.json nem preferência temporária.

### Evidência real de áudio

- Inventário: uma entrada e uma saída físicas Realtek, além dos aliases do SO.
  Entrada validada: índice 5/DirectSound/16 kHz; saída: índice 3/MME/24 kHz.
  Índices são resolvidos a cada sessão; não foram persistidos na configuração.
- Saída DirectSound aceitou 600 ms sem consumir tempo nem drenar; MME consumiu
  aproximadamente 652 ms na escrita e 251 ms na drenagem. Não foi forçado uso
  da API que só retornava sucesso sem evidência de transporte nesta máquina.
- Teste de 660 Hz: 96000 frames de loopback/48 kHz, RMS 0,020752 e 94% da
  potência espectral na banda do tom. Isso verifica o sinal no caminho digital,
  não por si só que a pessoa o ouviu. O usuário não ouviu o tom inicial.
- Teste simultâneo mic/saída: 24576 frames de entrada, pico 269, RMS 35,4.
  Era um teste de fluxo/ruído, sem fala confirmada; não foi usado como aceite
  de transcrição ou justificativa para amplificar automaticamente o microfone.
- Voz Windows existente → WAV → PCM 24 kHz → saída Realtek: 249054 bytes,
  cerca de 5,19 s, com a frase pública de teste. Usuário respondeu “Ouvi
  claramente”. Saída de voz foi confirmada por humano; provedor/configuração
  do assistente não foi trocado por causa desse teste local.
- Nenhum áudio bruto persistido, enviado ou transcrito externamente nestes
  testes. Sem instalação ou alteração de política de rede/credenciais.

### Verificação de código

- 15 testes novos de roteamento/limpeza/cache/volume/formato, três cenários Qt
  adicionais (startup fullscreen, teste sem sobreposição e fechar por sinal),
  além de assert de encerramento do runtime. Regressão selecionada: 279 testes
  em 24 módulos passaram em 21,68 s. Sintaxe e whitespace verificados.
- O teste local de voz não valida Gemini/STT online. O WinError 10013 ainda
  impede a conversa completa e a suíte asyncio neste executor. Há evidência
  histórica de conexão/microfone/reprodução no lançamento pelo Windows, mas
  isso não foi tratado como um novo teste end-to-end da versão corrigida.

## Modo orb em tela cheia e pop-ups — 14/11/2026

Pedido adicional do usuário: tela cheia apenas com orb; funções com avisos
pequenos e expansão sob demanda. Implementado em gui/immersive.py, com hooks
Qt em gui/window.py/gui/hud.py, façade em ui.py, plugin display_control.py,
parser local core/display_commands.py e ligação no comando digitado main.py.

- Fullscreen via F11/estado real da janela. Preserva visual normal e layout,
  inclusive retorno para janela maximizada. Orb utiliza Reactor3D existente,
  sem grade/labels/waveform ou importação de recursos de terceiros.
- Avisos 268×76 no canto inferior direito; até três; temporizador de 7 s.
  Resultado completo só ao pedir/abrir. Até 24 resultados por sessão, com
  snapshots HTML de texto/revisão/progresso. Atualizações do mesmo título são
  agrupadas; histórico e widgets são limitados. Sem reexecutar a função.
- Clique Abrir, Ctrl+O, “abra o último pop-up” ou título/ID. Popup flutuante
  com ampliar, recolher e fechar. Esc recolhe primeiro e sai do fullscreen
  depois; Ctrl+Espaço mostra um campo de comandos somente quando solicitado.
- Quiz interativo e mídia reutilizam widgets existentes, reparentados no Qt
  e devolvidos ao painel original. Estados/respostas do quiz são preservados.
- Confirmação mantém o gate humano original, sem ação accept por modelo.
  Aviso persistente abre os botões originais; cancelamento/expiração removem
  o aviso. Indicador PARAR gravação não é escondido e câmera ativa possui
  aviso fixo, dispensável apenas ao encerrar a captura.
- JinxUI.control_display apenas emite sinal; display_state devolve cópia de
  dados Python. Ferramenta espera no máximo 0,75 s pela confirmação de Qt e
  não afirma done quando apenas enfileirou a mudança. Plugin não importa Qt.
- Testes: 12 cenários Qt e 5 de parser/contrato/ack passaram; total selecionado
  de 261 testes passou em 19,50 s. Sintaxe/whitespace verificados. Sem instalação
  de pacote, gravação, câmera real, envio externo ou alteração de credenciais.
- Aplicativo reaberto; F11, aviso pequeno, Ctrl+O com conteúdo completo e Esc
  verificados pela interface real. Screenshot interno confirmou orb isolado e
  centralizado, com cor atual do usuário. App deixado nesse modo para teste.
  Comandos por voz adicionados ao catálogo; escuta física não foi aprovada,
  pois o bloqueio WinError 10013 da sessão de voz permanece neste executor.

## Correções após tentativa de teste — 14/11/2026

- Corrigida a criação incondicional de duas views WebEngine escondidas no
  construtor do HUD, causa observada do encerramento nativo 0x80000003.
  Rosto/núcleo agora iniciam sem WebEngine; modo web é opt-in e carrega apenas
  a view escolhida. Não houve alteração no sandbox do Chromium. Sem assets
  copiados/baixados; preferência salva e arquivos anteriores preservados.
- Disponibilidade do visual também rege o botão HUD, eliminando indicação de
  um modo web quando o que está efetivamente visível é o rosto nativo.
- A sondagem limitada de loopback produziu PermissionError/WinError 10013 em
  connect(127.0.0.1). O problema externo continua presente; ele não foi tratado
  como um defeito de microfone/provedor nem resolvido mudando regras de rede.
- core/voice_runtime.py é o ponto usado pelo runner existente: conexões locais
  com timeout, autenticação do par, sockets fechados, erro visível no HUD e no
  log, exceções sanitizadas. asyncio.run continua sendo o runtime normal.
  O programa evita entrar no accept() sem prazo do Python quando a sondagem
  já demonstrou a recusa. Também captura falhas de construção/inicialização.
- main.py delega o runner a esse módulo e faz comandos digitados reexibirem
  o motivo de indisponibilidade. gui/widgets.py inclui estado ERROR visível.
- INICIAR_JINX.cmd permite abertura normal pelo Windows no ambiente existente,
  com logs/desktop-start.log. Não foi usado para executar fora das restrições
  do executor. Nenhuma permissão de rede, chave ou biblioteca foi modificada.
- 8 testes de runtime e 3 testes Qt passaram. Regressão selecionada ampliada:
  244 testes em 21 módulos passaram em 9,21 s. Sintaxe/whitespace verificados.
  Suíte completa permanece bloqueada; preflight agora registra diretamente
  WinError 10013 em logs/internal_checks/environment.json, sem repetir o hang.
- Verificação real de UI: main.py iniciado sem flag especial, janela JINX
  encontrada e painel VOZ INDISPONÍVEL com a causa observado via acessibilidade.
  Processo manteve HUD, 21 ações e 27 plugins, sem rejeições de plugins.
  Isso valida a correção de inicialização/diagnóstico, não a conversa por voz.

## Retomada de 14/11/2026 — 5.1, 5.2 e 6.1

### 5.1 — Interrupção por voz

- core/barge_in.py, plugins/barge_in.py, main.py, core/echo.py,
  providers/engine_pipeline.py; testes em tests/test_barge_in.py.
- Integração real no callback do microfone: opção salva carregada no início,
  classificação CPU com EchoGuard, fala sustentada e uma interrupção por fala.
  Mute, modo telefone, repouso e push-to-talk fechado impedem classificação
  e envio. A thread do microfone agenda o cancelamento no loop de voz.
  Blocos iniciais da frase são preservados e repassados após o cancelamento.
- Corrigido o formato mono (frames, 1) do sounddevice na análise espectral:
  antes, o broadcasting criava uma matriz e invalidava a máscara de frequências.
  O teste usa o mesmo formato bidimensional do microfone.
- Pipeline cancela geração e descarta áudio/texto antigo já enfileirado,
  preservando chamadas de ferramenta em curso. Evento de fim encerra o estado
  de interrupção; Live também reconhece o ACK interrupted sem turn_complete.
  Interrupção pelo botão agora agenda operações de filas/tasks no loop de voz.
- Para testar: reinicie; em configurações dos plugins, INTERROMPER POR VOZ,
  ative e clique APLICAR. Peça uma resposta longa e fale sobre ela. Em inglês:
  enable voice interruption, ask for a long answer and speak over it.
  Se push-to-talk estiver ativo, mantenha a tecla pressionada.
- Seis testes passaram, inclusive eco sintético e voz distinta. Sem pacote
  novo. A detecção registra tempo observado, com latência adicional do
  dispositivo. Não há alegação de menos de 150 ms ou teste físico aprovado.

### 5.2 — Perfil e acessibilidade do navegador

- actions/browser_control.py; tests/test_browser_expansion.py.
- Automação usa somente LOCALAPPDATA/JINX/browser_profiles/<browser> no
  Windows (equivalentes dedicados em macOS/Linux). Não lê nem copia perfis
  pessoais. Sessões mantêm logins feitos especificamente nessa janela JINX.
  Abertura simples via sistema continua sendo uma entrega nativa não confirmada.
- Nova ação snapshot usa aria_snapshot da árvore acessível. Snapshot e texto
  da página são conteúdo não confiável. Não instala navegador/binário.
  Inicialização propaga falhas; timeout cancela a ação pendente. Saída de
  processos nativos vai para logs/browser-native.log.
- Testar: “Leia a árvore de acessibilidade desta página” / “Get an
  accessibility snapshot of this page”, usando browser_control snapshot.
- Sete testes passaram com operações assíncronas imediatas simuladas, sem
  simular um event loop funcional. Navegação/árvore reais ainda não verificadas.

### 6.1 — Preferências aprendidas

- core/learned_rules.py, plugins/learned_rules.py e core/session_preferences.py;
  tests/test_learned_rules.py.
- Propostas ficam em memória até revisão e confirmação local no HUD. Modelo
  não possui ação accept nem parâmetro que confirme. Listar, revisar, rejeitar
  e remover por ID; armazenamento próprio em config/learned_rules.json,
  independente da memória de fatos. Escrita atômica com leitura de confirmação,
  corrupção preservada e desfazer que não sobrescreve mudanças posteriores.
- Preferências de estilo/fluxo entram no prompt Live e pipeline com fronteira
  de conteúdo não confiável e sem mudar permissões/segurança/confirmações.
  Aceitação também notifica a sessão ativa pelo canal existente dos plugins.
- Testar: “Proponha a preferência de responder com frases curtas”; “Liste
  as preferências propostas”; “Revise a preferência de ID ...”, e confirme
  no HUD. Inglês: “Propose a preference for concise replies”, “List pending
  preferences”, “Review preference ID ...”. Seis testes específicos passaram.
  Sem modelo novo ou dependência adicional. Teste real por voz pendente.

### Validação e limite do executor

- Regressão selecionada: 233 testes passaram em 19 módulos, incluindo os
  três módulos novos e as integrações de Fase 4. Não é a suíte completa.
- Smoke Qt offscreen: quatro módulos importados e dois plugins executados
  em worker com uma QApplication no thread principal, sem warnings Qt.
- Os sete timeouts anteriores foram reproduzidos também em um programa
  mínimo, sem importar o app: asyncio.run(asyncio.sleep(0)). O traceback trava
  em socket._fallback_socketpair/accept na criação do ProactorEventLoop.
  Nenhum teste ou event loop foi substituído para afirmar aprovação.
- tests/run_internal_checks.py agora faz esse preflight isolado, salva o
  diagnóstico em logs/internal_checks/environment.json e retorna código 2
  se bloqueado, preservando os resultados anteriores. A opção explícita
  --run-despite-preflight permite repetir a suíte mesmo nessa condição.
- Sintaxe e whitespace dos arquivos alterados verificados. Nada enviado ao
  GitHub, nenhuma conta conectada e nenhum dispositivo real acionado.
  Fases 6.2–8.3 permanecem pendentes, assim como aceite real de voz/serviços.

## 3.4 — Pesquisa de voos
- core/flight_search.py, actions/flight_finder.py e tests/test_flight_search.py.
- Rota/data validadas, modos search/price/research existentes, painel com fontes e link de busca codificado; remove rota/data fixa embutida no URL antigo. Datas inválidas não viram “hoje” silenciosamente. save mantém relatório Desktop com undo.
- Testar “Pesquise voos de GRU para Lisboa em 1 de fevereiro de 2030” / “Search flights from GRU to Lisbon on February 1, 2030”. Quatro testes, busca externa simulada e limites verificáveis. Nenhuma dependência/conta nova.
- Preços/disponibilidade continuam unverified até consultar companhia; snippets ou links não viram reserva/cotação confirmada. Nenhuma compra ou abertura automática de navegador. A busca real depende dos backends públicos e do provedor configurado.

## 3.3 — Assistente de reuniões
- core/meeting.py, plugins/meeting_assistant.py, indicador Qt em gui/window.py/ui.py, tests/test_meeting.py.
- Start/stop/status explícitos; captura só após confirmação técnica de exibição do indicador PARAR. Duas trilhas mic/loopback iniciadas por barreira, redução 48k→16k, PCM em disco temporário com RAM limitada, máximo 30 min. Áudio bruto removido após processamento; transcript/resumo no diretório de documentos com undo por hash.
- Testar “Comece a gravar a reunião” / “Start recording the meeting”; “Pare a gravação da reunião” / “Stop meeting recording”. O botão visível PARAR também interrompe. Configurar Whisper local já em cache ou Groq em audição; nenhum modelo é baixado automaticamente. Groq envia áudio à sua conta configurada.
- SoundCard opcional via cartão REUNIÕES (instalador recusa plano >20 MB). Se loopback ou STT não estiver disponível, recusa captura em vez de gravar só metade silenciosamente. Alternativa: configurar Groq ou modelo local existente; áudio real depende de drivers/dispositivos compartilhados.
- Seis testes, inclusive ciclo completo com duas trilhas sintéticas, resumo simulado pela ladder e arquivo real. Teste de interface/indicador separado. Não gravada conversa real. Timestamps aproximados, sem diarização; sons do próprio JINX podem entrar na trilha sistema. Driver travado mantém indicador até encerrar a captura; stop/processamento é assíncrono e status parcial é explícito.
- SoundCard instalado sob demanda pelo callback do cartão: 0,04 MB; indicador Qt show/ack/hide passou sem abrir gravador.

## 3.2 — Legendas e resumo do YouTube
- core/youtube_summary.py, plugins/youtube_summary.py, actions/youtube_video.py, tests/test_youtube_summary.py.
- URL validada, legenda pela API atual com idioma PT/EN prioritário e fallback para idiomas existentes; timeout HTTP, limite de conteúdo e dados untrusted antes da ladder. Resumo no painel; reprodução HUD preservada. Rota antiga summarize usa a nova implementação, sem Tk na thread de trabalho; save mantém arquivo Desktop com undo.
- Testar “Resuma este vídeo: https://www.youtube.com/watch?v=...” / “Summarize this YouTube video: ...”. Cinco testes, incluindo API atual, falhas e caminho legado. youtube-transcript-api já instalado, import lazy e instalador opcional no cartão de legendas.
- Sem garantias para vídeos sem legendas, privados ou bloqueados pelo YouTube; ausência é unverified. Não confunde legenda com análise de imagens. Resumo real/voz pendente de vídeo/serviço acessível.

## 3.1 — Documentos e PDF
- core/office.py, core/optional_packages.py, plugins/office_suite.py, tests/test_office.py.
- PPTX com layouts e notas; DOCX com títulos/listas/tabelas; XLSX com fórmulas reais e recálculo no Excel. Conteúdo por JSON ou ladder configurada, sem modelos fixos. PDFs merge/split por seleção de páginas/extract; arquivos novos sem sobrescrever, reabertos antes da entrega, undo por hash.
- Testar “Crie uma apresentação de cinco slides sobre eletrônica” / “Create a five-slide presentation about electronics”; “Una estes PDFs”. Saída padrão Documentos/JINX, configurável no cartão DOCUMENTOS.
- Oito testes com arquivos reais temporários e recusa de quantidade errada de slides. python-pptx/python-docx/openpyxl já instalados; pypdf opcional instalado sob demanda pelo callback do cartão (0,40 MB). Instalador só aceita plano PyPI com hashes e <=20 MB; requirements padrão inalterado.
- Conversão automática Office→PDF depende de LibreOffice instalado (ausente nesta máquina). Alternativa: exportar PDF no Office. Nenhum pacote pesado instalado. Excel recalcula fórmulas ao abrir; não foi alegado cálculo pelo openpyxl. Conteúdo gerado por LLM/voz real depende da configuração/conta do usuário.

## 2.6 — Jogos instalados
- core/games.py, plugins/game_launcher.py, tests/test_games.py: Steam registro/libraryfolders/manifests, Epic registro/manifests, Riot associated_client local (VALORANT/League).
- Usa launcher existente para URIs Steam/Epic; Riot Client com argumentos fixos. Nome/ID exato, verificação de instalação e observação de processo na pasta do jogo. Sem instalar/comprar jogos.
- Testar “Liste meus jogos instalados” / “List installed games”, “Abra o jogo [nome exato]”. Quatro testes de manifests/escape/ambiguidade; sem lançar jogo real. Nenhum pacote novo.
- Formatos não reconhecidos/lojas ausentes podem produzir lista vazia; timeout de 3 s é unverified, não falha presumida. Riot depende de metadata associando executável e cliente. Voz real pendente.

## 2.5 — Watchers de preço, site e RAM
- core/watchers.py, plugins/system_watchers.py, main.py e tests/test_watchers.py.
- Dez monitores opt-in no máximo, consulta >=60 s, timeout 5 s, deduplicação por episódio; alertas respeitam quiet hours/mute/conversa. Site usa HEAD sem redirecionar; rede privada recusada pelo limite existente. Cota/erro de API nunca vira cotação.
- Testar: “Monitore RAM acima de 90%”, “Ative os alertas dos monitores”; “Monitore bitcoin acima de 500000 reais” / “Watch RAM above 90 percent”. Remover pelo ID/listar e desfazer suportados.
- Sete testes específicos; rede simulada para alertas. Nenhum pacote novo. CoinGecko público pode limitar acesso; sites que bloqueiam HEAD podem parecer indisponíveis. HTTP 2xx/3xx significa resposta HTTP, não integridade da página. Nenhuma negociação.
- Monitor de notícias legado preservado; novo plugin é a rota explícita de cripto, conforme backlog. Endpoint: https://coingecko-api-v3.readme.io/v3.0.1/reference/simple-price. Testes reais de serviço/voz pendentes.

## 2.4 — Contexto da janela ativa
- core/foreground_context.py, plugins/foreground_context.py, main.py e providers/engine_pipeline.py; tests/test_foreground_context.py.
- Privacidade opt-in via cartão/voz e undo; somente app/título/PID, sem screenshot. Metadados não confiáveis enviados a cada mudança (amostra 5 s), sem gerar fala espontânea no pipeline.
- Testar: “Ative o contexto da janela”, depois “O que é isso?” / “Enable window context”, “What is this?”. Desativar interrompe novas capturas; não apaga conteúdo já enviado.
- Três testes específicos; padrão desligado não chama APIs de captura. Sem pacote novo. Janela pode mudar antes da resposta; contexto não é visão e pode ficar desatualizado. Voz real pendente.

## 2.3 — Brilho por monitor
- Implementado em actions/monitor_brightness.py; testes em tests/test_monitor_brightness.py.
- Lista monitores WMI por identidade exata; escrita com leitura de confirmação e undo protegido contra mudanças posteriores. Não redireciona um monitor ausente para outro. Controle global legado preservado.
- Testar: “Liste meus monitores” / “List brightness monitors”, depois “Coloque o brilho deste monitor em 60%”.
- Dependências novas: nenhuma. API documentada em https://learn.microsoft.com/en-us/windows/win32/wmicoreprov/wmimonitorbrightnessmethods.
- Cinco testes passaram; consulta real detectou painel WMI a 100%. Escritas testadas com simulação, sem modificar o brilho real. Monitores externos sem WMI são unverified; use controle físico/global existente.

## Continuação — tarefas 6.2–8.3

Implementação local concluída em 14/11/2026, seguindo a ordem do plano. A
correção da tela preta do visual EVO foi expressamente adiada pelo usuário e
permanece aberta.

- **6.2 Autorreparo:** `core/self_heal.py`, `core/boot_sentry.py` e
  `plugins/self_heal.py`. Desligado por padrão; só sugere correção para arquivos
  Python permitidos até 12 KB, apresenta revisão no HUD, exige confirmação
  humana e salva backup/recuperação. Arquivos maiores são recusados para evitar
  substituição sem contexto completo. Não altera os arquivos de confirmação,
  undo ou segurança.
- **6.3 Criação de skills:** rascunho limitado e inerte para revisão; não salva,
  registra nem executa o conteúdo produzido.
- **6.4 Agente de desenvolvimento:** mudanças e execução exigem confirmação no
  HUD; caminhos do projeto gerado são limitados à pasta aprovada e só é permitido
  executar um único arquivo de entrada Python/Node, sem comando de shell. CLI
  Claude é apenas detectada quando já está instalada; não é chamada nem
  instalada automaticamente. Dependências geradas não são instaladas
  automaticamente; saída nativa vai para log local.
- **6.5 Regras aprendidas:** já implementada antes desta retomada; propostas
  continuam pendentes de revisão/confirmação do usuário.
- **7.1 Presença:** detecção local e opt-in, sem identificação ou gravação de
  frames, usando a câmera do app quando disponível.
- **7.2–7.3 Fitness:** lembrete de postura e contagem experimental de flexões
  dependem do pacote opcional MediaPipe. Não instalado: o instalador mantém o
  limite de 20 MB e a função informa indisponibilidade sem ele.
- **7.4 Alimentação:** registro local com totais, edição e desfazer. Estimativa
  por foto só envia a imagem quando o usuário pede explicitamente; não grava
  automaticamente o resultado estimado.
- **7.5 Eletrônica:** guia para DHT11 e Arduino Pro Mini com validação de tensão;
  mostra ligações/código e não grava firmware no dispositivo.
- **8.1 Radar local:** visual de mapa/círculo com fontes públicas, raio e
  frequência limitados; falhas de rede ficam explícitas.
- **8.2 Android:** dashboard emparelhado ganhou shell PWA instalável, logout e
  remoção explícita de dispositivo. É um app web instalável; nenhum APK/SDK foi
  criado ou instalado.
- **8.3 Atualizações:** desligadas por padrão. Verificação de release estável,
  hash SHA-256 obrigatório, revisão/confirmação antes de aplicar e rollback no
  próximo início. Arquivos de chaves, dados, segurança, confirmação e undo são
  excluídos. Nenhum release real foi baixado ou aplicado.

### Evidência e pendências

- 23 testes focados passaram: `test_autonomy_features.py` (10),
  `test_remaining_implementation.py` (7) e `test_learned_rules.py` (6). A
  execução usou `unittest`; `pytest` não está instalado. Compilação Python
  passou. O filtro do atualizador também bloqueia caminhos críticos no estágio,
  na aplicação e na recuperação.
- Não houve instalação de MediaPipe/SDK, atualização, publicação no GitHub,
  acesso a conta externa, captura de câmera real nem acionamento de hardware.
- A PWA precisa ser instalada e validada em Android real. Radar e presença
  precisam de validação com rede/câmera reais. Estimativas de foto e propostas
  de reparo precisam de chave/serviço de modelo acessível. A atualização real
  depende de haver release com asset ZIP e digest SHA-256 no formato esperado.
- **Aberto:** corrigir e validar o visual EVO que fica com tela preta, quando
  retomarmos esse item. As demais tarefas de implementação listadas no plano
  estão concluídas localmente; os pontos acima são validações externas/opcionais.

## Padronização da marca e regressão completa — 14/11/2026

- Branding antigo em comentários e histórico de versões foi atualizado para
  JINX; o cabeçalho de `LICENSE` agora identifica JINX sem mudar os termos CC
  BY-NC 4.0 nem o nome do titular dos direitos.
- Créditos, URLs e nomes do projeto de origem permanecem em `NOTICE.md`, na
  atribuição do README e no plano, conforme a licença. A frase/modelo de wake
  word pré-treinado continua sendo “Hey Jarvis”; renomear só o texto não muda
  o modelo acústico e poderia deixar a documentação falsa. Logs históricos
  também foram preservados.
- Regressão completa dos 34 módulos: 27 passaram, 0 falharam e 7 expiraram no
  limite. O preflight independente registrou WinError 10013 ao criar o event
  loop local. Os módulos com timeout usam `asyncio.run`; um teste de reunião
  filtrado também ficou preso aguardando a thread concluir esse trecho. Esse
  bloqueio ambiental impede afirmar que toda a suíte ou a voz está aprovada.
- `logs/internal_checks/results.json` e os logs individuais registram os
  resultados. Não foi aplicada política de rede alternativa nem substituído o
  event loop para mascarar o bloqueio.


## Teste de voz do usuário (14/11/2026)

- Resultado informado pelo usuário: "tudo funcionou 100%". Os comandos exatos testados não foram especificados.
- Inicialização com `.venv-local` (Python 3.13.17): sem erros de importação; plugins e ações carregados (26 plugins, 21 ações).
- Pendências observadas no log, sem relação com a voz:
  - Cota do Gemini esgotada: todos os modelos de texto estavam em pausa. Notícias e demais funções que dependem do Gemini não responderam. Corrigir com nova chave ou aguardar a cota.
  - Saída de áudio: o host `directsound` foi ignorado por não mover áudio; o sistema usou `mme`.
  - Busca de notícias: DuckDuckGo sem resultados, com fallback para busca de texto, também sem resultados.
- Não verificado: funções que dependem do Gemini, serviços externos com contas reais e transcrição Groq com chave real.
