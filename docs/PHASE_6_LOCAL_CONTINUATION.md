# Fase 6 — continuação local (15/11/2026)

## Escopo e preservação

Plano consultado: assets/extras/IMPLEMENTATION_PLAN.md. Fase 6.1 foi preservada;
seu aceite manual foi informado pelo usuário. Alterações preexistentes em rotinas,
assets e regras aprendidas não foram revertidas. Nenhum commit ou push realizado.

## 6.5 — extração automática de fatos

core/memory_extraction.py reconhece frases completas e conservadoras em PT-BR/EN
para nome, cidade, profissão e projeto atual. Não chama modelo nem transmite dados.
main.py observa texto digitado autorizado e transcrições completas do usuário
(o pipeline também emite transcrições). Saídas de ferramentas/modelos não são
fontes de extração. Não se trata de um extrator semântico universal.

Em ⚙ → Memória, o novo painel mostra propostas e o valor anterior quando houver.
Somente o botão humano Aprovar e salvar persiste uma proposta; Rejeitar descarta.
Não há ferramenta de aprovação para o modelo. As propostas são limitadas a 16,
ficam apenas em RAM e desaparecem ao fechar o processo. Repetições são suprimidas
por uma janela de 128 observações propostas/rejeitadas; não há bloqueio permanente.
Isso não modifica a ferramenta explícita save_memory já existente.

Fatos e regras de comportamento continuam separados. O reconhecimento recusa
perguntas, citações usuais, múltiplas frases e padrões comuns de segredos; isso
é uma heurística limitada, não um detector completo de dados sensíveis.
Uma alteração posterior do fato impede aceitar uma proposta desatualizada.
Desfazer restaura o valor anterior somente se a entrada não mudou depois.
O store factual usa atualização protegida por lock e substituição atômica do JSON.

Teste manual pendente nesta retomada: dizer “Meu nome é Jones”, abrir ⚙ → Memória,
conferir que não foi salvo, rejeitar; depois dizer “Moro em Recife”, aprovar,
conferir o fato e solicitar desfazer. Em inglês: “My current project is JINX-IA”.
O painel existente de fatos pode precisar ser reaberto para refletir uma aprovação.

## 6.4 — agente de desenvolvimento

Inspecionado actions/dev_agent.py e core/code_checks.py. Preservados confirmação
humana, leitura das regras do projeto, verificações e ausência de instalação
automática de dependências. Agora o caminho aprovado é passado resolvido ao job,
caminhos absolutos gerados são recusados e escritas geradas verificam alterações
intervenientes. Desfazer não sobrescreve arquivos modificados posteriormente.
Se a infraestrutura de testes não puder ser importada, o resultado é marcado
como não verificado, em vez de ser anunciado como aprovado.

As verificações de concorrência são otimistas; não garantem isolamento contra
outro processo que altere o arquivo exatamente entre conferência e escrita.
Claude CLI permanece opcional, detectada e não invocada/instalada automaticamente,
conforme o escopo de adaptação do plano. Execução de código confirmada usa as
permissões do usuário; não equivale a isolamento de filesystem/rede.

## 6.2 — autorreparo

Inspecionados self_heal, boot_sentry, _repair_check e plugin. Já existiam opt-in,
proteção de arquivos, revisão completa, confirmação, hashes, validação funcional
em cópia temporária antes da troca, backups, marcador e recuperação pré-Qt.
Acrescentados recusa de candidato sem mudanças e descarte explícito (action reject,
candidate_id), para liberar a fila limitada. Nenhum módulo de boot/segurança alterado.
Testes usam fixtures: não foi quebrado deliberadamente o aplicativo instalado.

## 6.3 — Skill Forge

Mantido o escopo aprovado pelo plano: gerar Markdown inerte para revisão, sem
registro, execução ou disponibilização a agentes de fundo. Acrescentada recusa
de blocos de código dentro do rascunho, além das validações existentes.
Sem prova de isolamento Windows, execução de skills geradas continua pendente
e não deve ser anunciada como implementada.

## Validação

Novos testes em tests/test_memory_extraction.py cobrem PT-BR/EN, consentimento,
rejeição, repetição, fatos existentes, limites, cópias defensivas, conflitos,
desfazer, painel Qt offscreen, falha de escrita atômica, caminhos gerados,
preservação de edição intermediária, validação indisponível, autorreparo sem
mudanças/descarte e recusa de código no Skill Forge.

Comando da suíte completa (Python local 3.14.10):
`.jinx_runtime/envs/3.14.10/Scripts/python.exe tests/run_internal_checks.py`
QT_QPA_PLATFORM=offscreen e PYTHONIOENCODING=utf-8.
Resultados detalhados em logs/internal_checks/results.json e logs por módulo.
Consultar esses resultados para a rodada final; testes simulados/offscreen não
substituem aceite humano de voz, interface visível ou serviços reais. Nenhuma
dependência nova, instalação, conta externa ou hardware foi utilizado para provar
as funcionalidades. Não há alegação de cobertura total ou ausência de defeitos.


### Resultado final observado

- Suíte interna: 41 módulos aprovados, zero falhas, zero timeouts.
- Unittest: 461 testes contabilizados, 460 aprovados e 1 skip (pypdf opcional).
- Testes novos desta continuação: 14 aprovados.
- Autoteste separado `python -m providers._tests`: 99 aprovados, zero falhas;
  saída em logs/internal_checks/providers-self-test.log.
- Análise sintática dos 10 arquivos Python desta alteração: aprovada.
- `git diff --check`: aprovado. Ruff não está instalado no Python local;
  nenhuma dependência foi instalada para esta verificação.
- Voz e interface visível das funcionalidades novas: aceite manual pendente.
