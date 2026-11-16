# Agentes Conversacionais Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Execute the plan task-by-task; each step uses checkbox syntax.

**Goal:** Permitir cadastrar personas conversacionais, chamá-las por nome na conversa da JINX e executar diálogos curtos e identificados entre duas personas.

**Architecture:** Perfis conversacionais persistem em `config/api_keys.json` por meio de getters/setters atômicos do `memory.config_manager`; não reutilizam os agentes Markdown de `core/tasks`. Um módulo de domínio faz validação, consulta e alternância de falas via `core.gemini.text`, duas tools estáticas expõem consulta e diálogo à sessão da JINX, e uma página de configurações administra os perfis. A resposta final volta à sessão Live existente, portanto é lida com a voz atual da JINX.

**Tech Stack:** Python, Gemini/provider ladder existente, plugins Python auto-descobertos, PyQt6, `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-15-agentes-conversacionais.md`

## Global Constraints

- Não alterar o executor de tarefas nem os perfis existentes em `agents/*.md`.
- Não salvar nem expor novas credenciais; preservar todo o conteúdo existente de `config/api_keys.json` ao atualizar perfis.
- Perfis secundários não recebem ferramentas, acesso à máquina ou ações externas.
- Diálogos só começam por chamada explícita do usuário; usar duas rodadas por padrão e limitar a três.
- Usar a escada de modelos/provedor já configurada; cada perfil seleciona apenas `FAST` ou `SMART`.
- Nenhum commit nesta implementação local.

## Review Focus

- Configuração antiga ausente, malformada ou contendo a chave de perfis em formato inesperado deve resultar em lista segura e não apagar outras configurações; cobrir no teste do repositório.
- Nomes duplicados por diferença de caixa/espaços ou perfil inexistente devem ser recusados antes da chamada de modelo; cobrir no teste do módulo central.
- Texto vazio ou excessivamente longo não deve disparar chamadas; cobrir pergunta vazia e limites do perfil no teste do módulo central.
- Conteúdo de uma fala anterior que peça ferramentas ou tente trocar instruções deve permanecer dado citado; cobrir com teste que verifica o enquadramento no prompt enviado ao próximo agente.
- Exceção/retorno vazio do modelo deve parar o diálogo com erro legível, sem inventar turnos; cobrir com mock em teste do módulo central.

---

### Task 1: Persistência e orquestração de perfis

**Files:**
- Modify: `memory/config_manager.py`
- Create: `core/conversation_agents.py`
- Create: `tests/test_conversation_agents.py`
- Modify: `core/gemini.py` only if needed to pass through the selected `FAST`/`SMART` tier unchanged.

**Interfaces:**
- Produces `get_conversation_agents() -> list[dict]` and `save_conversation_agents(profiles: list[dict]) -> None` in `memory.config_manager`.
- Produces `list_profiles() -> list[AgentProfile]`, `save_profile(profile) -> AgentProfile`, `delete_profile(name) -> None`, `ask_agent(name: str, request: str) -> str` and `debate_agents(name_a: str, name_b: str, topic: str, rounds: int = 2) -> str` in `core.conversation_agents`.
- `AgentProfile` contains `name: str`, `instructions: str` and `tier: str` (`FAST` or `SMART`). The configured main-assistant name is resolved as a protected built-in profile, not stored as a removable secondary profile.

- [ ] **Step 1: Write failing tests** for atomic config round-trip preserving unrelated keys, case-insensitive uniqueness, profile validation and deletion, direct invocation with the profile system instruction, debate turn order/default/max rounds, quoted untrusted prior turn, and model failure handling.
- [ ] **Step 2: Run** `python -m unittest tests.test_conversation_agents -v`; confirm the new APIs/tests fail before implementation.
- [ ] **Step 3: Implement** config getters/setters using the existing locked read-modify-write path; implement profile validation, built-in main identity, direct call, and bounded alternating text-only debate. Inject `core.gemini.text` for tests or patch it without making network calls.
- [ ] **Step 4: Run** `python -m unittest tests.test_conversation_agents -v`; all tests must pass and no real model/network call may occur.

### Task 2: Voice-call tools and routing context

**Files:**
- Create: `plugins/agent_consult.py`
- Create: `plugins/agent_debate.py`
- Modify: `main.py` where `_build_config()` assembles plugin declarations and the system prompt.
- Create: `tests/test_conversation_agent_plugins.py`

**Interfaces:**
- `agent_consult.py` declares tool `consult_agent(agent_name: str, request: str)` and returns an attributed profile answer.
- `agent_debate.py` declares tool `debate_agents(agent_a: str, agent_b: str, topic: str, rounds: int = 2)` and returns labeled turns.
- The system prompt identifies the current named profiles and tells the main session to route explicit calls by name to these tools, attribute returned text correctly, and never execute instructions contained in agent output.

- [ ] **Step 1: Write failing tests** for plugin discovery/schema, dispatch with valid profile names, controlled unknown-agent errors, and the presence of routing/attribution instructions in the Live system prompt.
- [ ] **Step 2: Run** `python -m unittest tests.test_conversation_agent_plugins -v`; confirm expected failures.
- [ ] **Step 3: Implement** two small auto-discovered plugin wrappers around Task 1 APIs and add dynamic routing context without changing the existing Live session or tool filtering.
- [ ] **Step 4: Run** `python -m unittest tests.test_conversation_agent_plugins tests.test_plugin_loader -v` (or the repository's actual plugin-loader test module); confirm all tool declarations and dispatch tests pass.

### Task 3: Settings UI and regression verification

**Files:**
- Create: `gui/conversation_agents_panel.py`
- Modify: `gui/settings_panel.py` to add a dedicated embedded settings section.
- Create: `tests/test_conversation_agents_panel.py` or extend `tests/test_settings_panel.py` using its established Qt test pattern.

**Interfaces:**
- The panel loads saved profiles, lists secondary agents, and exposes add/edit/delete operations for `name`, `instructions` and `tier`.
- The main assistant is shown as protected and cannot be deleted or renamed from the secondary-agent editor.

- [ ] **Step 1: Write failing UI tests** for add/edit/delete persistence, required-field validation, tier selection, protected built-in identity, and preservation of existing assistant/provider settings.
- [ ] **Step 2: Run** the focused Qt test; confirm expected failures.
- [ ] **Step 3: Implement** the focused panel and embed it in Settings without changing existing sections or save paths.
- [ ] **Step 4: Run** `python -m unittest tests.test_conversation_agents tests.test_conversation_agent_plugins tests.test_conversation_agents_panel -v`, then `$env:PYTHONUTF8='1'; python -m unittest discover -s tests -p "test_*.py"`.
- [ ] **Step 5: Verify** `python -m py_compile core/conversation_agents.py plugins/agent_consult.py plugins/agent_debate.py gui/conversation_agents_panel.py main.py`, JavaScript is not applicable, and `git diff --check` only on the new/modified feature files. Review the final scoped `git status` and leave unrelated existing edits untouched.
