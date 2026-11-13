# Histórico de alterações

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
