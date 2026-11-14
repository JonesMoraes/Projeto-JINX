# Agenda principal: Google Agenda

Em 14/11/2026, a agenda padrão do JINX passou do Trello para Google Calendar.
O arquivo local memory/agenda.json foi preservado. O temporizador legado
Trello foi desativado; nenhuma lista, cartão, evento ou credencial foi apagado.

## Conectar

1. Use o seu cliente OAuth Desktop do Google Cloud com Calendar API habilitada.
   Guarde o JSON em config/google_client_secret.json (fora do Git).
2. Abra Configurações → Agenda. O calendário padrão é primary (principal da
   conta). Para outro calendário, informe o ID ao qual a conta tem acesso.
3. Marque Permitir sincronização manual, confirme o nome do JSON e salve.
4. Clique Conectar conta Google no navegador e autorize sua conta. O login usa
   a integração Google Workspace existente e os serviços que você selecionou
   nas configurações Google; não ativa Gmail/Drive automaticamente.
5. Use Sincronizar Google Agenda para enviar/receber eventos.

A conta desta instalação não estava conectada e o JSON OAuth não estava
presente durante a mudança. Nada foi enviado ao Google nos testes ou na
troca de configuração. Não compartilhe JSON de cliente, tokens ou chaves no chat.

## Comportamento

- A ferramenta agenda_sync e o botão do painel apontam para Google por padrão,
  mesmo se houver um ID de lista Trello antigo nas configurações.
- Adicionar/editar/arquivar e desfazer operam localmente. Pedir explicitamente
  sincronização é que envia/recebe dados. Arquivar/desfazer não apaga eventos
  no Google; um evento remoto poderá reaparecer após uma sincronização.
- Sem polling automático Google. A ferramenta de voz responde imediatamente
  e entrega o resultado pelo painel/voz quando a sincronização termina.
- Google Calendar mantém vínculos próprios, IDs estáveis, escrita condicional
  e detecção de conflito da integração já existente. Conflitos preservam dados.
- Eventos de dia inteiro e recorrências continuam fora da reconciliação desta
  versão. Eventos locais novos têm duração padrão de 30 minutos ao exportar.
- Tarefas do organizador continuam locais; não é uma integração Google Tasks.
- Trello permanece disponível como ferramenta independente. A agenda não
  retorna automaticamente ao Trello se faltar conexão Google.
- O painel apresenta mensagem de sincronização legível, sem as instruções
  internas do protocolo de resultados destinadas ao modelo.

## Verificação

417 testes aprovados no Python 3.15.2, com API/OAuth simulados. Cobertura nova:
roteamento sem fallback Trello, configuração antiga, Google desativado, erro
de conta, preservação local, CRUD/undo sem envio, execução de voz assíncrona
e campos Google na interface. Testes Trello legados usam seleção explícita.
Render do painel Windows conferido sem dados pessoais. Evidência local:
logs/google-agenda-default-tests.log.

Consentimento, sincronização e edição reais no Google ainda dependem de
configuração/autorização do usuário e não foram declarados validados.
