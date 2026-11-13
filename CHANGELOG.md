# Histórico de alterações

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
