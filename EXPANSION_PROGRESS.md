# Execução local — Fases 2 e 3

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
- Sete testes com arquivos reais temporários. python-pptx/python-docx/openpyxl já instalados; pypdf opcional instalado sob demanda pelo callback do cartão (0,40 MB). Instalador só aceita plano PyPI com hashes e <=20 MB; requirements padrão inalterado.
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
