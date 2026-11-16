# Acesso Remoto Mobile e Pareamento Persistente — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Melhorar o painel remoto no celular e manter o dispositivo confiável entre reinicializações, até sair ou revogar.

**Architecture:** Separar o armazenamento local dos pareamentos do servidor HTTP. Persistir somente SHA-256 do token de dispositivo e chave de sessão protegida em repouso (DPAPI no Windows; AES-GCM com chave privada em outros sistemas), com escrita atômica; manter tokens bearer temporários com TTL atual de 12 h. Atualizar as páginas móveis sem trocar rotas, operações ou identidade visual escura/índigo.

**Tech Stack:** Python 3.14, FastAPI, `cryptography`, Win32 DPAPI (`pywin32` já listado como dependência Windows), HTML/CSS/JavaScript nativo, `unittest` e cliente de teste do FastAPI.

**Spec:** `docs/superpowers/specs/2026-11-15-acesso-remoto-mobile.md`

## Global Constraints

- Preservar as rotas/endpoints atuais, chaves `jinx_token`, `jinx_key`, `jinx_device_token`, PWA e as funções de voz, arquivo, comando e ativação.
- Manter TTL de bearer token em 12 horas; somente o pareamento confiável é durável e revogável.
- Não persistir token de dispositivo em texto aberto no servidor; não persistir chave de sessão em texto aberto.
- Não adicionar dependências; tokens/segredos não podem aparecer em logs.
- Não apagar ou sobrescrever silenciosamente um arquivo de pareamentos ilegível; falhar fechado.
- Não modificar nem incluir no commit as outras alterações locais que já existem no repositório.

## Review Focus

- Reinicialização do servidor com registro íntegro: o dispositivo ainda renova sua sessão sem nova chave.
- Arquivo de registro truncado ou ciphertext inválido: nenhuma autorização concedida e dados originais preservados.
- Aparelho compartilhado: usuário pode desmarcar lembrar e não deixa pareamento durável.
- Rede indisponível durante auto-reconexão: token local é preservado para uma nova tentativa; somente 401/revogação remove o vínculo.
- Teclado virtual/viewport estreito: chave de 8 caracteres e controles não devem cortar nem ficar sob a safe area.

---

### Task 1: Persistência segura dos dispositivos autorizados

**Files:**
- Create: `dashboard/device_store.py`
- Modify: `dashboard/server.py`
- Test: `tests/test_dashboard_remote_access.py`

**Interfaces:**
- `DeviceSessionStore(data_dir: Path | None = None)` guarda registros duráveis; `register(device_token: str, session_key: str) -> None`, `resolve(device_token: str) -> str | None`, `remove(device_token: str) -> bool`, `clear() -> int`, `__len__() -> int`.
- `DashboardServer(device_store: DeviceSessionStore | None = None)` usa o store padrão em produção e um store injetado nos testes.
- Caminho padrão: `%LOCALAPPDATA%/JINX/remote-access` no Windows; `~/Library/Application Support/JINX/remote-access` no macOS; `${XDG_DATA_HOME:-~/.local/share}/jinx/remote-access` no Linux. Os testes passam um diretório temporário.
- Arquivo `remote_devices.json`, versão 1: mapa de `sha256(device_token)` para ciphertext da chave de sessão; gravação atômica. Windows usa DPAPI; macOS/Linux usam AES-GCM e arquivo `remote_devices.key` privado ao usuário (0600).
- Se o arquivo for ilegível ou falhar de autenticação, a inicialização preserva o arquivo e bloqueia novas gravações/autorizações lembradas até recuperação ou revogação explícita; nunca substitui o registro silenciosamente.

- [x] **Step 1: Escrever testes vermelhos do store e das rotas** — cobertura de serializar/reabrir, não expor token/chave, token inválido, `remove`, `clear` e preservação do arquivo corrompido.
- [x] **Step 2: Escrever teste de integração de reinicialização** — parear via `/auto-login`, criar outro `DashboardServer` com o mesmo store e confirmar que `/api/device-login` emite uma sessão válida.
- [x] **Step 3: Conectar login manual** — aceitar `remember` no corpo de `/login`; quando verdadeiro, registrar token aleatório e retorná-lo junto da sessão; quando falso, manter login temporário.
- [x] **Step 4: Conectar QR/login/logout/revogação** — persistir token de QR, buscar registros persistidos em `/api/device-login`, remover o pareamento em `/api/device-unpair` e limpar store em `/api/revoke-devices`; preservar o contrato de manter a sessão do autor da revogação.
- [x] **Step 5: Executar os testes de persistência e segurança** — `python -m unittest tests.test_dashboard_remote_access -v`; esperado: todos aprovados.

### Task 2: Entrada de autorização e shell mobile

**Files:**
- Modify: `dashboard/static/login.html`
- Modify: `dashboard/static/app.html`
- Modify: `tests/test_dashboard_remote_access.py`
- Verify: `tests/test_remaining_implementation.py`

**Interfaces:**
- Entrada manual mantém POST `/login` e envia `{pin, remember}`; resposta opcional `device_token` é armazenada somente se `remember` foi selecionado.
- QR segue em `/auto-login`; o storage key `jinx_device_token` não muda.
- Shell mantém feed e controles existentes; reorganiza markup do compositor apenas para uma grade responsiva.

- [x] **Step 1: Adicionar teste de contrato da chave de 8 caracteres e da opção remember.**
- [x] **Step 2: Corrigir o formulário mobile** — alinhar `maxlength`, validação e auto-submit a 8 caracteres; apresentar checkbox compreensível; mostrar mensagens de rate-limit/erro; não apagar token salvo em falha de rede transitória.
- [x] **Step 3: Reorganizar o painel para viewport mobile** — usar `100dvh`, safe-area, cabeçalho compacto, feed rolável e compositor em linhas, com alvos táteis de 44 px, foco visível e movimento reduzido.
- [x] **Step 4: Executar verificações de contrato e regressão** — `python -m unittest tests.test_dashboard_remote_access tests.test_remaining_implementation -v`; esperado: todos aprovados.

### Task 3: Validação integrada

**Files:** nenhum novo; revisar os arquivos das Tasks 1–2.

- [x] **Step 1: Verificar segurança por inspeção** — rotas existentes preservadas, tokens hashed/protegidos no disco, logs não contêm valores secretos, logout/revogação realmente removem dados.
- [x] **Step 2: Executar suíte completa** — `python -m unittest discover -s tests -p "test_*.py"`; em console Windows, usar `PYTHONUTF8=1` se a página de código CP1252 impedir impressão dos testes de memória.
- [x] **Step 3: Executar `git diff --check` e `py_compile` dos módulos Python tocados; revisar o diff para preservar alterações alheias já presentes.**

**Commit:** Não criar commit nem fazer push: o repositório já contém alterações locais de outras tarefas não relacionadas.
