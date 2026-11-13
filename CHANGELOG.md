# Histórico de alterações

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

- Auditoria estática e mapeamento completo em IMPLEMENTATION_PLAN.md.
- Baseline de inicialização, conexão de áudio e consulta local registrado em BASELINE.md; teste falado PT-BR/EN confirmado pelo usuário.
- Git local e branch feature/expansion preparados; exclusão de assets Brahma, arquivos locais e dados pessoais do versionamento.
- Nenhuma funcionalidade nova, alteração de segurança ou dependência instalada nesta fase.
