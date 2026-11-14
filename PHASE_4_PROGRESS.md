# Fase 4 — integrações de serviços

Retomada autorizada pelo usuário em 13/11/2026. Implementação iniciada pela
tarefa 4.1. Tarefa 4.2 implementada localmente; a Fase 4 permanece em andamento,
com aceite real/voz pendente. 4.3 tem ponte de leitura/revisão local implementada.
Atualização de 14/11/2026: também há código local de 4.4–4.7: casa
inteligente, geração de imagens, leitura/sugestões Instagram e upload YouTube.
O último commit local é 9d9c8d7, da tarefa 4.5. Os cenários simulados de
tests/test_phase4_completion.py passaram na retomada. Contas/dispositivos
reais, envio/publicação confirmados e voz ainda não encerraram o aceite.
Instagram limita-se à leitura profissional e sugestões locais.

## 4.3 — Discord: caixa de entrada e revisão local

Arquivos: core/discord_bridge.py, plugins/discord_bridge.py,
tests/test_discord_bridge.py. Implementação nova baseada na documentação
oficial, usando requests já instalado; sem discord.py ou pacote novo.

Cartão DISCORD começa desligado. Configurar token de BOT (não conta pessoal),
ID do servidor, canal e 1–10 IDs de usuários separados por vírgula. O canal deve
ser texto do servidor configurado, com negação explícita de Ver Canal para
@everyone. Administradores e outros membros com permissões específicas ainda
podem acessar o canal no Discord; a allowlist limita mensagens importadas,
não modifica permissões do servidor. O bot precisa de acesso ao canal/histórico
e do intent Message Content para o conteúdo, conforme exigências do Discord.

Comandos: “Consulte minha caixa de entrada Discord” / “Read my Discord inbox”;
“Revise a mensagem Discord de ID ...” / “Review Discord message ID ...”.
Consulta explícita das últimas 20 mensagens; bots/webhooks/autores fora da
allowlist são ignorados. Conteúdo externo permanece untrusted. Revisão mostra
autor/canal/texto no HUD e usa confirm.request. Após confirmação local,
reconsulta conteúdo e permissões; edição, troca de conta/canal/allowlist ou
desativação invalidam a revisão. Apenas encaminha para discussão local;
execução de ferramentas remotas e respostas enviadas ao Discord não estão
implementadas. Não existe polling ou conexão automática no boot.

11 testes específicos passaram: defaults, filtros, canal público/servidor
incorreto, alteração da configuração, revisão sem HUD, edição após confirmação,
transporte sanitizado, ausência de redirects/retry e contrato do carregador.
Nenhuma mensagem real foi lida/enviada, nenhum servidor teve permissões
alteradas. Consentimento/configuração real, voz e aceite de ponta a ponta
permanecem pendentes; esta seção não declara toda a Fase 4 concluída.

Referências: https://docs.discord.com/developers/resources/channel e
https://docs.discord.com/developers/resources/message.

## 4.1 — Google Workspace

Arquivos: core/google_workspace.py, core/google_calendar_sync.py,
plugins/google_workspace.py, tests/test_google_workspace.py.

- Cartão GOOGLE gerado pelo gerenciador existente, sem criar widgets em plugins.
  Serviços começam desligados. OAuth Desktop no navegador somente pelo botão
  da interface, PKCE, retorno em 127.0.0.1/porta aleatória e limite de 180 s.
  Consentimento parcial não substitui a conexão anterior. Refresh com timeout.
- Gmail lista metadados e lê texto simples. Envio requer endereço exato, revisão
  do texto completo no painel e confirmação local existente; parâmetros do
  modelo não confirmam. Troca de conta/configuração invalida a operação pendente.
  O resultado só é done após observar o ID na pasta SENT. Confirmação perdida
  ou falha de rede não causa repetição automática do envio.
- Calendar lista próximos eventos e sincroniza a agenda por comando explícito,
  após ativar a opção de sync. Vínculos/shadows próprios não apagam o dirty do
  Trello. IDs de criação determinísticos evitam duplicação após timeout; ETag
  e If-Match protegem atualizações concorrentes. Fuso explícito obrigatório.
  Conflitos, exclusões remotas, recorrências e dia inteiro são preservados ou
  informados como parciais. Arquivar/desfazer localmente não apaga no Google;
  um evento remoto existente poderá reaparecer numa sincronização posterior.
- Drive lista somente arquivos acessíveis por drive.file e cria texto UTF-8
  (até 50000 caracteres). Multipart/related, readback de nome/tamanho/checksum.
  Undo envia à lixeira somente se conteúdo/versão não mudou e há ETag; nunca
  apaga permanentemente nem altera compartilhamento. Não há Picker nesta etapa:
  a listagem normalmente começa vazia e mostra arquivos criados pelo JINX.
- Chamadas de rede rodam em thread, uma operação por vez, e retornam de imediato.
  Resultado e falha chegam ao painel/voz; status recupera a última operação.
  Dados externos entram como untrusted. Falhas não expõem exceções com tokens.

### Configuração manual

1. No seu Google Cloud, habilite Gmail API, Calendar API e Drive API conforme
   os serviços desejados. Configure consentimento/usuário de teste e crie um
   cliente OAuth do tipo Desktop. Não compartilhe suas credenciais.
2. Salve o JSON em config/google_client_secret.json. No cartão GOOGLE,
   selecione apenas os serviços desejados e clique CONECTAR NO NAVEGADOR.
   Envio inclui gmail.readonly para verificar a pasta Enviados. Gmail readonly
   e send, calendar.events e drive.file são os escopos usados, sob demanda.
3. Autorize sua conta no navegador. Token local em config/ (já ignorado pelo
   Git); api_keys.json só é atualizado pelo config_manager da UI existente.
4. Teste: “Liste meus cinco últimos e-mails” / “List my five latest emails”,
   “Leia o e-mail de ID ...” / “Read email ID ...”, “Liste meus próximos eventos”
   / “List my upcoming events”, “Sincronize minha agenda com o Google” /
   “Sync my agenda with Google”, “Crie um arquivo de texto no Drive chamado ...”.
   Nenhum desses comandos foi afirmado como validado por voz nesta máquina.

### Validação e bloqueios

Testes específicos usam somente biblioteca padrão, dados fictícios, arquivos
temporários e APIs simuladas. Comando: `python -m unittest discover -s tests
-p test_google_workspace.py -v`. O resultado atualizado consta abaixo.

- 39 testes específicos passaram, incluindo descoberta/schema do plugin,
  OAuth/refresh simulados, envio confirmado/cancelado, falhas sanitizadas,
  paginação/conflitos de agenda, recuperação de POST ambíguo, multipart Drive,
  checksum e undo que preserva edição posterior.
- Os quatro arquivos Python novos passaram na análise sintática; diff das
  alterações de documentação passou sem erros de whitespace.
- Regressão agenda/Trello: 14 dos 16 testes passaram; dois não executaram a
  verificação esperada por ausência de requests no Python disponível. Não se
  trata de resultado aprovado para a suíte completa nem de validação real.

Ambiente na primeira tentativa de 4.1: .venv foi copiado de outro usuário e aponta para um Python
3.12 ausente. Python 3.13 e 3.15 locais não têm as dependências do aplicativo;
extensões nativas existentes em .venv são de 3.12. Não foi alegado startup,
smoke Qt ou regressão completa. A tentativa autorizada de recuperar o Python
3.12 portátil (10,6 MB, fonte oficial) foi bloqueada por DNS no executor e por
permissão salva no navegador. Nenhum runtime foi instalado; HUD não abriu.

Contas Google reais, consentimento, refresh real, entrega de e-mail,
sincronização remota, undo remoto e voz PT-BR/EN permanecem unverified.
Nenhuma mensagem, arquivo ou evento real foi enviado/criado nos testes.
As bibliotecas Google já constam em requirements.txt e não foram alteradas.
Na retomada de 4.2, requirements.txt foi verificado no .venv-local (Python
3.13.17), sem dependências faltantes ou conflitos no pip check. pypdf 7.1.0 e
SoundCard 0.4.6 foram instalados de cópias locais após verificar hashes RECORD.
Os 39 testes Google passaram nesse ambiente; contas/voz reais continuam pendentes.
Nenhum módulo protegido de confirmação/undo foi modificado.

Branch/commit: criação de feature/phase-4-services recusada pelo filesystem
(acesso de escrita a .git negado). Alterações permanecem no workspace, junto
das alterações preexistentes preservadas; nenhum commit ou push foi feito.

### Referências de implementação

- https://developers.google.com/identity/protocols/oauth2/native-app
- https://developers.google.com/workspace/gmail/api/auth/scopes
- https://developers.google.com/workspace/gmail/api/guides/sending
- https://developers.google.com/workspace/calendar/api/guides/version-resources
- https://developers.google.com/workspace/calendar/api/v3/reference/events/insert
- https://developers.google.com/workspace/drive/api/guides/manage-uploads

## 4.2 — Spotify

### Verificação interna ampliada após autorização de execução contínua

Adicionado tests/run_internal_checks.py: executa cada módulo em processo
isolado com timeout, registra logs e results.json em logs/internal_checks/ e
retorna falha se qualquer módulo falhar ou exceder o prazo. Comando executado:
`.venv-local\Scripts\python.exe tests/run_internal_checks.py --timeout 15`.
Resultado: 14 módulos passaram, zero módulos terminaram com erro e sete
atingiram timeout. Timeout não é aprovação: bateria, Edge TTS, integração,
contexto da janela, Groq STT, reuniões e preferências de sessão seguem pendentes.
Esses módulos incluem caminhos asyncio; o diagnóstico anterior identificou
bloqueio na criação de socketpair do event loop no executor Windows.
Nenhum teste foi desabilitado ou alterado para produzir aprovação.
Esta rodada amplia a validação da base; não implementa as tarefas 4.3–8.3.

Arquivos: core/spotify.py, plugins/spotify_control.py, tests/test_spotify.py.

- Cartão SPOTIFY pelo gerenciador existente: Client ID e permissões de leitura,
  playlists e controle, todas desligadas inicialmente. OAuth somente pelo botão
  da interface; PKCE S256 sem Client Secret, state, listener 127.0.0.1 com porta
  dinâmica e prazo de 180 s. Token em config/spotify_token.json, fora do Git.
  Consentimento parcial/configuração alterada preservam a conexão anterior.
- Refresh serializado, timeouts HTTP, endpoints fixos, sem redirects nem retry
  de comandos. Trocar conta, Client ID ou permissões invalida clientes antigos.
  Erros de transporte não expõem tokens, códigos de autorização ou URLs.
- Lista dispositivos e playlists (limite/offset explícitos, sem seguir URLs de
  paginação). Consulta reprodução; play/pause/next/previous/transfer com ID
  exato ou único dispositivo ativo não restrito. Playlist por URI exato.
  Leitura posterior verifica dispositivo, reprodução, playlist/faixa conforme
  comando; ACK HTTP sozinho não significa sucesso. Estado atrasado permanece
  unverified, sem repetir automaticamente a alteração.
- Alternativa explícita media_key: toggle/next/previous/stop reutiliza ações
  existentes. Sempre unverified: teclas globais podem controlar outro aplicativo.
  Nunca aciona essa alternativa automaticamente após falha da API.
- Plugin retorna imediatamente, aceita uma operação por vez, entrega resultado
  ao painel/voz e permite consultar status. Conteúdo externo entra como untrusted.
  Não cria widgets nem toca a interface fora dos métodos thread-safe de player.
- Sem spotipy nem pacote novo; usa requests já declarado. LibreOffice/FFmpeg
  independentes não são necessários para esta tarefa. Sem cópia de código externo.

### Configurar e testar

1. Crie seu app no Spotify Developer Dashboard. Registre o Redirect URI
   http://127.0.0.1/callback (sem porta, para permitir a porta dinâmica).
2. No cartão SPOTIFY, informe Client ID, selecione as permissões desejadas e
   clique CONECTAR NO NAVEGADOR. Não é necessário Client Secret.
3. Abra o Spotify em um dispositivo. Diga “Liste meus dispositivos Spotify” /
   “List my Spotify devices”, “Liste minhas playlists Spotify” /
   “List my Spotify playlists”, “Pause o Spotify” / “Pause Spotify”.
   Para playlist/dispositivo específico, use o URI/ID obtido pela listagem.
4. Alternativa sem API: peça explicitamente “Use a tecla de mídia para próxima
   faixa” / “Use the global media key for next track”. Pode afetar outro app.

O modo de desenvolvimento exige Premium do proprietário e usuários permitidos
na allowlist; controle de reprodução também exige acesso Premium. Restrições
do Spotify podem impedir o uso mesmo com Client ID válido. Nenhuma conta foi
conectada, faixa reproduzida, tecla real enviada ou cota consumida nos testes.

Validação específica: 28 testes passaram (OAuth/PKCE simulado, refresh,
mudança de conta/permissões, erros HTTP, verificação de reprodução, paginação,
retorno assíncrono e ausência de fallback automático). Descoberta/schema do
plugin e cartão passaram; import não carregou Qt; sintaxe dos três arquivos OK.
Regressão conjunta Spotify/Google/agenda-Trello: 83 testes passaram em 2,66 s.
A suíte completa excedeu 120 s; diagnóstico com faulthandler localizou o bloqueio
no teste de bateria que chama asyncio.run: socket._fallback_socketpair fica em
accept ao inicializar o ProactorEventLoop do Windows, antes do código assíncrono
do teste. Não foi modificado o aplicativo para contornar essa limitação do
executor. Regressão completa/startup/voz permanecem não aprovados nesta retomada.
pip check sem conflitos; diff das documentações sem erros de whitespace.
Aceite por voz, leitura/controle reais e consentimento continuam unverified.
Sem commit/branch: .git permanece somente leitura para o executor.

### Referências Spotify

- https://developer.spotify.com/documentation/web-api/tutorials/code-pkce-flow
- https://developer.spotify.com/documentation/web-api/concepts/redirect_uri
- https://developer.spotify.com/documentation/web-api/concepts/quota-modes
- https://developer.spotify.com/documentation/web-api/reference/get-a-users-available-devices
- https://developer.spotify.com/documentation/web-api/reference/get-a-list-of-current-users-playlists
- https://developer.spotify.com/documentation/web-api/reference/start-a-users-playback
