# Plano de expansão do JINX-IA

Data: 13/11/2026. Estado: auditoria estática inicial concluída; plano apresentado para revisão. Nenhum código de funcionalidade alterado nesta tarefa.

## Escopo e sequência

Executar Fase 0, depois 1–8 na ordem fornecida. Uma tarefa por commit, relatório após cada tarefa e branch por fase. Este documento não declara funcionalidades concluídas apenas porque há arquivos semelhantes. A implementação começa após a revisão deste plano solicitada pelo usuário.

Diretório real: `C:\Users\Windows 10 MF\JINX IA`. A pasta em Documents contém somente `_provider_import_stage`, não a aplicação. Git está instalado, mas o projeto real não contém `.git`.

## Arquitetura conferida

| Área | Evidência e integração real |
|---|---|
| Inicialização e voz | `main.py`; `ui.py` cria a interface Qt; voz executa em thread/event loop separado. Preservar uma QApplication e os sinais para a thread Qt. |
| Ações | `core/action_loader.py`: `TOOL` contém name, description, parameters e handler callable; descoberta isolada por arquivo. Handler recebe apenas contextos que declara. Suporta metadados tier/brief para orçamento. |
| Plugins | `core/plugin_loader.py`, `plugins/_template.py`: contrato PLUGIN + run(parameters, player=None, session_memory=None). Não usar TOOL em lugar de PLUGIN nessa pasta. |
| Compatibilidade | `ui.py` reexporta símbolos públicos dos módulos gui. Preservar exports e assinaturas existentes. |
| LLM | `core/gemini.py`: call, text, as_json, parse_json; fallback e caminhos de provedor configurado já existem. Rotação deve integrar esse caminho, não criar cliente paralelo em plugins. |
| Segurança | `core/confirm.py`: request/resolve com callbacks da UI; `core/undo.py`: push_undo; `core/outcome.py`: done/unverified/failed, started, ask, untrusted. Usar essas APIs, sem alterar suas regras sem autorização. |
| Provedores | `providers/registry.py`: módulos listados por categoria, importados sob demanda; contratos em base.py; schema.py administra orçamento; painel em gui/providers_panel.py. |
| Tarefas | `core/tasks/{engine,agents,brain,tools,web,research,desktop,store}.py`, agentes Markdown em agents/. Conferir isolamento por caminho e capacidades antes de qualquer extensão; não presumir que o nome desktop concede autorização. |
| Persistência | `memory/config_manager.py` administra api_keys.json; `memory/memory_manager.py` e long_term.json guardam memória. .gitignore já exclui chaves, tokens e parte dos dados pessoais. |
| Instalação | `core/installer.py` já usa find_spec, mas contém dependências pesadas na lista automática; requirements.txt também inclui WebEngine, OpenCV, Playwright e bibliotecas de documentos. |

## Divergências e decisões necessárias

1. O sistema informa Windows 10 build 19045, Python 3.12.10, PyQt6/WebEngine 6.11.0. Hardware confirmado na Fase 0: Core i5-6200U, cerca de 8 GB RAM e Intel HD 520, distinto do Ryzen/16 GB/RX580 descrito. Implementar detecção real e guardas Windows; não prometer APIs exclusivas do 11. ML em CPU com consumo conservador.
2. A UI foi traduzida para PT-BR; main.py contém preferência falada fixa em PT-BR. Há detecção de idioma no STT, mas não foi encontrada uma camada única de localização de toda a UI. Será necessário suporte compartilhado PT-BR/EN em novas telas e respostas, preservando o padrão PT-BR; não assumir mecanismo completo existente.
3. Groq já aparece como preset API em providers/stt_whisper.py. EdgeTTSEngine já existe em core/tts.py, mas não como provedor TTS listado em registry.py. As tarefas 1.7–1.8 serão integração e validação, não duplicação.
4. Existem browser_control.py, flight_finder.py, file_processor.py e dev_agent.py; suas capacidades devem ser comparadas com os critérios antes de extensão.
5. Há assets Brahma e carregamento/download no HUD. A nova regra proíbe reutilizá-los. Não copiar, estudar nem adaptar mais código desses projetos. Antes do primeiro commit de funcionalidades, propor desativação reversível da integração e retirada dos assets do conjunto versionado; qualquer exclusão definitiva requer autorização. Um substituto independente só pode nascer de especificação funcional aprovada, sem consultar o código de origem. Não rotular o visual atual como implementação independente.
6. Dependências pesadas já presentes não serão reinstaladas ou removidas nesta auditoria. Para atender o novo padrão, planejar a separação de dependências opcionais e instalação explícita na UI; mostrar tamanho estimado de bibliotecas, modelos e binários antes de instalar qualquer item acima de ~20 MB.
7. Tokens OAuth e sessões persistentes de serviços são segredos: manter material de autenticação sob config/ e fora do Git; guardar caminhos/referências em api_keys.json quando o SDK exigir arquivos próprios. Não duplicar chaves em logs ou no plano.
8. A implementação anterior do Brahma foi vista nesta conversa. Portanto não afirmar independência histórica absoluta de uma recriação; limitar o novo trabalho à descrição funcional aprovada e documentar procedência.

## Fase 0: tarefas e baseline

- 0.1 (esta tarefa): auditar e produzir este plano. Resultado verificado: contratos e arquivos consultados, pasta real e ausência de Git confirmadas. Baseline funcional ainda não executado.
- 0.2 (após revisão): inventariar hardware sem dados pessoais; ler inicialização para identificar downloads, rede e rotinas automáticas; lançar aplicação sem instalar pacotes; registrar startup, voz e uma ação inofensiva em BASELINE.md. Comandos: “Que horas são?” / “What time is it?” e consulta de sistema sem mutação. Voz só será marcada done com áudio capturado/transcrito e resposta reproduzida observáveis; se depender de fala do usuário ou chave/serviço disponível, registrar unverified e a limitação.
- Inicializar Git com baseline em branch principal, depois criar feature/expansion para Fase 0. Fazer staging por lista explícita, nunca git add indiscriminado. Excluir configurações, memória pessoal, arquivos de importação, logs, venv e assets proibidos; revisar índice antes de commit. Não inventar identidade Git se faltar configuração.
- Não modificar confirm.py, undo.py, regras de sandbox, excluir dados ou instalar >20 MB sem autorização específica. Consumir essas APIs em módulos novos não implica modificar os módulos protegidos.

## Mapa de implementação em ordem

Os nomes novos abaixo são propostas, sujeitos à revisão pontual do código no início de cada tarefa. Todos os handlers retornam resultados verificados, usam a fronteira untrusted para conteúdo externo, e respeitam undo/confirm conforme efeito.

| Tarefa | Arquivos/hooks existentes → extensão proposta | Aceitação e dependências |
|---|---|---|
| 1.1 Rotação de chaves | core/gemini.py, memory/config_manager.py, gui/window.py → core/gemini_accounts.py | 429 na chave A troca para B sem restart; cooldown por chave separado do cooldown por modelo, concorrência segura, segredos mascarados. Teste com respostas simuladas, sem consumir cota para provocar 429. Sem pacote novo. |
| 1.2 Trello e sync | plugins/trello_control.py, core/agenda_sync.py novos; gui/window.py; persistência compartilhada de agenda | IDs estáveis, paginação, fusos, conflito, exclusão e idempotência; mudança para 17h deve reaparecer no remoto. requests existente. Como 1.3 vem depois, 1.2 cria apenas contrato/store mínimo de agenda que 1.3 completa; evitar dependência invertida. |
| 1.3 Organizer | plugins/organizer.py, core/agenda_store.py proposto; reminder.py e core/routines integrados sem lembretes duplicados | CRUD local atômico com undo e eventos de sync. Sem pacote novo. |
| 1.4 Cakto | plugins/cakto_sales.py, cartão de configuração | Consultar pedidos/vendas, sem movimentação financeira implícita; resultados de serviço real ou unverified. requests. |
| 1.5 Rastracking + encomendas | core/rastracking_client.py, plugins/rastracking.py e plugins/parcel_tracking.py | Escopo corrigido com o usuário: ambos, separados. Rastracking consulta vendas/clientes/suporte via API do usuário; encomendas via Correios autorizado ou site manual. Sem conta/servidor pessoal pré-preenchido. requests existente. |
| 1.6 Foco/humor/blocklist | três plugins; hooks de prompt e voz em main.py | Persistência, liga/desliga, PT/EN; regras de personalidade não podem anular segurança. Sem pacote novo. |
| 1.7 Groq STT | providers/stt_whisper.py, registry.py, gui/providers_panel.py | Reutilizar preset existente e oferecer configuração/teste de audição; confirmar transcrição real. HTTP existente. |
| 1.8 Edge TTS | core/tts.py → providers/tts_edge.py; registry e painel | Vozes PT-BR/EN e botão TESTAR; lazy import. edge-tts opcional; requer internet. |
| 2.1 Processos | actions/system_monitor.py e computer_control.py → ação compacta | Top CPU/RAM; preservar árvore JINX; fechamento gentil primeiro, confirmação antes de encerrar/forçar conforme regra do usuário. psutil existente. |
| 2.2 Bateria | system_monitor.py e rotinas | Carga/estado; desgaste apenas se informado pelo SO; desktop sem bateria retorna indisponível. Alertas configuráveis. Sem pacote pesado. |
| 2.3 Brilho | actions/computer_settings.py | WMI por monitor quando disponível; DDC/monitor externo pode não ser suportado. Informar limite e não inventar sucesso. Pacote WMI leve somente se necessário. |
| 2.4 Janela ativa | desktop.py, main.py, gui/window.py | Toggle privacidade, app/título, sem screenshot nem captura com toggle desligado. APIs Windows existentes. |
| 2.5 Watchers | actions/background_monitor.py, core/routines | CoinGecko/HTTP/RAM com intervalo mínimo, timeout, deduplicação, quiet hours; nenhum loop ocupado. requests/psutil. |
| 2.6 Jogos | open_app.py, game_updater.py | Ler registro/manifests Steam/Epic/Riot; lançar por instalação verificada e confirmar processo/janela. Sem pacote novo. |
| 3.1 Office/PDF | file_processor.py, file_controller.py → geradores modulares | Arquivos válidos com conteúdo, notas/fórmulas/tabelas; undo apenas dos arquivos criados, sem apagar mudanças posteriores. python-pptx/python-docx/openpyxl/pypdf opcionais. pypdf não converte Office nem renderiza páginas: exportação por aplicativo/LibreOffice instalado, senão limitação explícita. |
| 3.2 YouTube | youtube_video.py e file_processor.py | Legenda real → untrusted → ladder → painel. youtube-transcript-api opcional; indisponibilidade de legenda informada. |
| 3.3 Reuniões | audio_devices.py, providers STT, main.py, painel | Start/stop explícito, indicador gravação, mic+loopback sincronizados, resumo/itens; loopback WASAPI depende do dispositivo. Biblioteca adicional só após avaliar tamanho/permissão. |
| 3.4 Voos | flight_finder.py, web_search.py | Rota/data e fontes no painel sem API paga; distinguir preços observados de links de busca. Sem pacote novo. |
| 4.1 Google | core/google_workspace.py e plugin; gui, agenda_store/sync | OAuth desktop, escopos mínimos, refresh seguro; Gmail/envio confirmado, Calendar bidirecional, Drive. google-api-python-client e auth opcionais; consentimento necessário para conta real. |
| 4.2 Spotify | plugin, ações de mídia existentes | Dispositivos/playlists e controle por conta; fallback media keys. spotipy opcional. Algumas operações exigem Premium; client ID gratuito não garante reprodução remota. |
| 4.3 Discord | core/discord_bridge.py e cartão | Canal privado + allowlist, nenhuma ampliação de permissões; confirmação local preservada. discord.py opcional. |
| 4.4 Casa | plugin HA/Tuya | REST/estado confirmado, descoberta explícita, undo quando viável. requests e tinytuya opcional; depende de dispositivos/chaves locais. |
| 4.5 Imagem | core/gemini.py caminho multimodal e painel | Modelo escolhido/configurado pelo núcleo, imagem persistida/exibida; sem modelo local. Consumo de API e suporte da conta não garantidos. |
| 4.6 Instagram | integração isolada, OFF | Aviso explícito de risco na UI; leitura/sugestão; autorização delimitada antes de autoenvio, confirmação existente preservada. instagrapi opcional. |
| 4.7 Upload vídeo | cliente Google compartilhado, plugin | Upload local, metadados só quando pedidos, confirmação antes de publicação; verificar ID/visibilidade. Dependências da 4.1. |
| 5.1 Barge-in | main.py, providers/audio.py, core/echo.py, tts.py | VAD CPU opcional, cancelamento e descarte de buffer; medir latência em vez de prometer <150ms; testes com eco e PTT. webrtcvad compatível ou silero, pacote/modelo com autorização por tamanho. |
| 5.2 Browser | actions/browser_control.py | Comparar capacidades existentes; profile em LOCALAPPDATA, sem tocar perfis pessoais; snapshots acessíveis, ações e untrusted. Playwright/binário opcionais; navegador >20 MB exige aprovação. |
| 6.1 Regras | config_manager, main.py, plugin/painel | learned_rules.json distinto de fatos, listar/remover; regras são preferências, sem poder sobre políticas de segurança. Sem pacote novo. |
| 6.2 Autorreparo | core/self_heal.py e boot_sentry.py propostos; entrada mínima main.py | OFF, IMMUNE cobre segurança/boot, candidato em memória e temporário validado, backup atômico, histórico, rollback anterior ao Qt/LLM. Teste deliberado somente em fixture isolada. Alterar boot/sandbox protegido só após autorização concreta. |
| 6.3 Skill forge | features/, plugin forge, loader com aprovação específica | Subprocesso comum não é sandbox: isolamento real de filesystem/rede precisa prova no Windows; até lá geração para revisão sem execução/registro automático. Timeout/temp dir sozinhos não bastam. Nunca disponível em agentes de fundo. |
| 6.4 Dev agent | actions/dev_agent.py, agents/ definição foreground | Adaptar existente com workspace real resolvido, execução confirmada, sem registro como agente de fundo. CLI Claude opcional detectada, sem instalação automática. |
| 6.5 Memória | memory/memory_manager.py, main.py, painel | Propostas visíveis por heurística, aceitar/rejeitar antes de persistir. Sem pacote novo. |
| 7.1 Presença | screen_processor.py, captura compartilhada, painel | Haar local e consentimento visível; presença não identifica pessoa. OpenCV opcional, já consta na instalação atual. |
| 7.2 Postura | módulo monitor CPU e rotinas | OFF, indicador câmera, baixa frequência/resolução, quiet hours. mediapipe opcional com aprovação de tamanho. Estimativa de postura sem diagnóstico médico. |
| 7.3 Flexões | captura compartilhada, módulo pose | Contagem/feedback por regras geométricas e voz; calibrar ângulo, reconhecer oclusão. mediapipe da 7.2. |
| 7.4 Alimentação | plugin, store JSON local e painel | Totais/dia, ajustes/undo; foto via ladder com estimativa explícita. Sem modelo local/dependência pesada. |
| 7.5 Circuitos | screen_processor.py e visão ladder; gui/circuit_panel.py, pinouts JSON | DHT11/Pro Mini: esquema, pinos, fios e código; validar tensão/versão antes da orientação; código nunca gravado no hardware sem autorização. Qt existente. |
| 8.1 Globo/radar | nova visualização Qt opcional | Rotas, OpenSky e Overpass com limites, dados e idade visíveis; modo indisponível sem WebEngine. Implementação própria, nenhum asset Brahma. |
| 8.2 Android | dashboard/server.py, core/tls.py, gateway e projeto Kotlin | Pairing/token, revogação, confirmação por ação. Investigar primeiro restrições Android/Play para chamadas, notificações, clipboard e Accessibility; APIs indisponíveis terão alternativa explícita. SDK/Gradle/emulador pesados exigem aprovação. |
| 8.3 Atualização | bootstrap/update módulo, setup.py, scripts build e workflow novos | Opt-in; releases autenticadas/verificadas, staging/rollback, preservar config/memory/features. Repositório remoto e política de release precisam existir. PyInstaller opcional; não publicar nem enviar dados locais automaticamente. |

## Licenças e procedência

Única fonte externa autorizada para port é https://github.com/jgm-source/jarvis-opensource (fork MARK LV). README consultado confirma os plugins citados. Antes de portar: conferir LICENSE e notices de cada arquivo, fixar commit de origem e registrar arquivos/adaptações no NOTICE.md. Não clonar nem incorporar outros projetos para implementar o backlog. Manter licença e autoria de Mark-LVII já existentes.

## Verificação e entrega

Por tarefa: testes específicos com efeitos externos simulados, checagem sintática/import lazy, falhas/timeout/undo/confirm, comandos PT-BR e EN. Integrações reais só são done quando o efeito remoto/local for observado. Não enviar mensagens, publicar vídeos, executar pagamentos, terminar processos reais ou usar câmera/gravação para provar um teste sem a autorização aplicável.

Por fase: startup + voz + ação antiga + recursos novos; readme.md, NOTICE.md e CHANGELOG.md atualizados; merge local após verificações. Branches: feature/expansion (0), feature/phase-1-ports, feature/phase-2-system, feature/phase-3-productivity, feature/phase-4-services, feature/phase-5-voice-browser, feature/phase-6-autonomy, feature/phase-7-vision, feature/phase-8-stretch. Nenhum push/publicação implícito.

Relatório por tarefa: (1) implementado em 1–3 linhas; (2) arquivos; (3) comando PT-BR para testar e resultado real; (4) dependências opcionais/tamanho; (5) riscos e pendências. A fase permanece incompleta quando voz, serviço real ou aceitação obrigatória estiver unverified.

## Próximo passo após revisão

Atualização de execução: Fase 0 aceita pelo usuário; tarefas 1.1, 1.2 e 1.3
implementadas na branch feature/phase-1-ports. A tarefa 1.3 passou em 38 testes
incluindo regressões de 1.1/1.2 e smoke headless do painel. Aceitação por voz
das funcionalidades novas e integração Trello real seguem pendentes; não
confundir conclusão de implementação com conclusão da Fase 1. Próxima tarefa:
1.4 implementada: Cakto com campos vazios para configuração manual, 55 testes
passando e aceitação real/voz pendente. Tarefa 1.5 implementada com os dois
recursos separados conforme escolha explícita do usuário: 71 testes passando,
contas reais e voz pendentes. Próxima tarefa: 1.6, foco/humor/blocklist.

Executar 0.2: baseline controlado e Git local, registrar conflitos de licença/dependências e proposta reversível para o HUD. Não iniciar 1.1 antes de finalizar a Fase 0. Nenhuma alteração de segurança ou exclusão é autorizada por este documento.
