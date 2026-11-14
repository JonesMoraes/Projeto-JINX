# Revisão do JINX IA — 14/11/2026

Atualização após autorização “corrija e incorpore”: expansão e correções
incorporadas ao main local em 43f66d1, por fast-forward. Os 384 testes passaram.
Rollback, validação prévia do autorreparo, teste independente de assets e
comentários do sketch foram corrigidos; HUD recebeu fallback para falhas web.
Configurações e dados locais foram conferidos e preservados. Pendências de
escopo/validação externa continuam em [INTEGRACAO_EXPANSAO.md](INTEGRACAO_EXPANSAO.md).
O restante deste documento preserva os achados anteriores às correções.

## Resultado

As alterações da outra sessão existem no GitHub, mas não estão no aplicativo
aberto nesta pasta. O main local e origin/main estão em 9a40f6d, até a Fase 3.
A branch origin/feature/expansion-2026-11-14 está em
5bfef86b9df5a09c87881bc759cb044e64507dd2 e altera 91 arquivos
(8.147 linhas adicionadas e 558 removidas).

A revisão anterior desta conversa considerava somente main; a atualização das
referências remotas revelou a expansão posterior. Não foi feito merge,
checkout da aplicação, correção de código nem reinício do aplicativo.

## Verificação executada

- Atualização das referências Git e comparação entre main, remoto e expansão.
- Leitura do plano em EXTRAS ADD/IMPLEMENTATION_PLAN.md e dos relatórios das fases.
- Inventário de módulos, análise sintática e revisão dirigida de integração,
  recuperação, plugins, câmera, interface e funcionalidades novas.
- Main: 187 testes passaram; pip check sem conflitos.
- Expansão: 373 testes executados, 372 passaram e um falhou, sem skips.
  Execução com Python 3.12 do ambiente instalado, Qt offscreen, saída UTF-8
  e diretório temporário com caminho longo normalizado.
- Descoberta da expansão: 21 ações, 36 plugins válidos, nenhum plugin
  rejeitado; 24 seções de configuração. Análise sintática sem erros nos
  diretórios actions, plugins, core, gui, providers, dashboard, memory e tests.
- Reprodução adicional do erro de rollback usando somente arquivos temporários
  e lançamento de processo simulado.

A expansão foi examinada em worktree separado no diretório temporário
jinx-review-5bfef86. As credenciais da instalação não foram copiadas.
Não foram enviados e-mails, publicados vídeos, acionados equipamentos ou
usadas contas reais para validar as funcionalidades novas. Os testes com
serviços/áudio simulados não comprovam funcionamento dessas integrações reais.

## Achados prioritários

### P1 — Rollback do atualizador usa dois locais incompatíveis

core/update_apply.py:25 e :65 gravam backups e pending-update.json em
.jinx_update. core/boot_sentry.py:12–14 procura o marcador em
config/self_heal; :70 procura os backups sob esse mesmo diretório.
mark_update_healthy também remove o marcador do local diferente.

Consequência: se a versão atualizada não inicializar, a próxima abertura não
encontra a transação para restaurar. Na reprodução temporária com as mesmas
convenções dos módulos, _recover_update retornou False, o arquivo atualizado
continuou instalado e o marcador real permaneceu em .jinx_update.

O teste test_apply_rolls_back_on_next_boot_if_new_app_does_not_mark_healthy
passa com caminhos normalizados porque substitui STATE e UPDATE_MARKER pelo
diretório do atualizador; isso mascara a divergência dos valores de produção.
Corrigir os caminhos compartilhados e testar o contrato sem substituí-los
por valores inconsistentes com a configuração real antes de habilitar updates.

### P2 — Teste de HUD depende de assets ausentes em checkout limpo

tests/test_native_hud_startup.py:46–55 exige setUrl para EVO/ECHO sem fornecer
um arquivo temporário nem simular _orb_page_path. Esses assets não são
versionados. gui/hud.py:305–319 usa setHtml/obtenção do asset quando ele falta.

Foi a única falha na rodada completa normalizada. O teste precisa preparar
explicitamente um HTML temporário e cobrir a ausência dos arquivos separadamente.
Isso não comprova que o visual real funciona nem que todo o HUD está quebrado.
A tela preta do EVO continua explicitamente aberta no histórico de expansão.

### P2 — Exemplo Arduino contém diretivas inválidas

core/circuit_guide.py:23–25 inicia o sketch com linhas '# Install', '# Confirm'
e '# Never'. Em C++/Arduino, isso é interpretado como diretiva de
pré-processador inválida, e não comentário. O exemplo entregue não compila
como está; substituir essas linhas por comentários //.
O teste atual verifica texto/pinos, mas não a validade do sketch.

### P2 — Autorreparo só verifica sintaxe antes de efetivar

core/self_heal.py:73 e :111–130 usa ast.parse, troca o arquivo e remove o
marcador de recuperação imediatamente. Um candidato com sintaxe válida e
erro em importação ou execução pode ser confirmado como aplicado sem passar
por smoke test; não haverá marcador para recuperação automática no boot.

Há confirmação humana, backup e undo, mas isso não satisfaz a validação
funcional em temporário prevista na tarefa 6.2. Completar a validação antes
da troca e definir quando uma versão reparada pode ser considerada saudável.

## Conferência do plano

| Área | Evidência encontrada na expansão | Pendência ou limite |
|---|---|---|
| Fases 1–3 | Código anterior preservado e testes presentes | Aceites reais de contas e parte dos testes por voz continuam separados dos mocks. |
| 4.1 Google | OAuth, Gmail, Calendar sync e Drive; plugin e testes | Configurar e validar conta, consentimento e efeitos reais. Drive tem escopo drive.file, sem Picker amplo. |
| 4.2 Spotify | OAuth PKCE, dispositivos/playlists e controle verificado; testes | Conta e reprodução reais ainda não validadas nesta revisão. |
| 4.3 Discord | Consulta de inbox com allowlist e revisão local | Não há execução remota de ferramentas, resposta ao Discord ou polling; escopo é menor que uma ponte de comandos. |
| 4.4 Casa | Home Assistant/Tuya, leitura, escrita com readback e undo | Depende de configuração e dispositivos reais. |
| 4.5 Imagem | Núcleo Gemini, arquivo persistido e sinal para mostrar imagem | Modelos precisam ser configurados; não demonstra suporte à geração por qualquer provedor alternativo. |
| 4.6 Instagram | Leitura profissional e rascunhos | Envio/publicação não implementados; relatório assume deliberadamente esse escopo reduzido. |
| 4.7 YouTube upload | Cliente Google, revisão, confirmação e verificação de ID/privacidade | Upload real e processamento final no YouTube não comprovados. |
| 5.1 Interrupção | Gate CPU, eco e integração ao fluxo de áudio | Sem medição nova de latência física nesta revisão. |
| 5.2 Navegador | Perfil exclusivo, snapshots e testes | Fluxos reais com navegação e sites continuam pendentes de aceitação. |
| 6.1/6.5 Preferências | Propostas, revisão, confirmação e store separado | Não encontrada a proposição automática por heurísticas prevista para a memória 6.5; o caminho implementado é explícito. |
| 6.2 Autorreparo | Proposta, confirmação, backup e sentry | Validação funcional/recuperação precisa dos ajustes acima. |
| 6.3 Skills | Rascunho Markdown inerte | Não registra/executa skills; está alinhado à alternativa limitada prevista até existir isolamento comprovado. |
| 6.4 Dev agent | Confirmação, limites de caminho e entrada Python/Node | CLI Claude é apenas detectada; não existe integração de execução com ela. |
| 7.1 Presença | Haar local opt-in ligado aos frames da câmera | Teste real de câmera e ausência/presença pendente. |
| 7.2–7.3 Fitness | Postura/flexões locais com MediaPipe opcional | Modelo/dependência e câmera reais não validados; câmera/feedback exigem ensaio de ponta a ponta. |
| 7.4 Alimentação | Log, totais, edição, undo e estimativa solicitada por foto | Estimativa real por modelo não validada. |
| 7.5 Eletrônica | Guia textual DHT11/Pro Mini e código | Não há o painel de circuitos/pinouts estruturados previsto; exemplo tem erro de comentários. |
| 8.1 Radar | Consulta OpenSky/Overpass e desenho Qt local | Implementação reduzida: não é globo 3D com rotas; dados reais e idade da observação precisam de validação. |
| 8.2 Android | Manifest/service worker PWA, logout e revogação | Não há Kotlin, APK ou funções Android nativas do plano. Precisa de validação em celular e ambiente adequado à instalação web. |
| 8.3 Atualizador | Check, digest, staging e helper | Rollback defeituoso; sem pipeline de build/release versionado e sem atualização real validada. |

“Há código até a Fase 8” é correto. “Tudo do plano está concluído e aprovado”
não é sustentado pela revisão: existem adaptações de escopo, partes ausentes,
defeitos e validações externas pendentes.

## Outras dívidas e documentação

- A integração visual de terceiros permanece em gui/hud.py; os assets não
  acompanham o Git. Não foi tratada como implementação independente.
- Permanecem usos preexistentes de stdout/stderr DEVNULL em open_app.py e
  send_message.py e diálogo Tk legado em youtube_video.py. São dívidas em
  relação às regras do projeto, não regressões atribuídas à branch nova.
- PHASE_4_PROGRESS.md contém referências históricas a commits/ambientes
  anteriores e trechos dizendo que não houve push. O estado remoto atual é
  o commit 5bfef86. Os registros de 26 plugins também não representam o
  inventário atual: a descoberta desta revisão encontrou 36 válidos.
- Os sete timeouts de asyncio registrados na outra sessão não ocorreram
  aqui. A rodada inicial também expôs sensibilidade dos testes a caminhos
  curtos do Windows e encoding cp1252. A rodada final normalizou apenas o
  ambiente, sem alterar testes/código ou substituir o event loop.
- O plano foi movido localmente para EXTRAS ADD; o Git registra a remoção
  do caminho original. A movimentação e os arquivos pessoais preexistentes
  foram preservados.

## Ordem recomendada

1. Corrigir atualizador/rollback, exemplo Arduino e teste independente de assets.
2. Completar validação do autorreparo e alinhar os relatórios ao escopo real.
3. Integrar a branch revisada ao main em mudança própria, preservando dados locais.
4. Reiniciar no código integrado e validar HUD/áudio e funcionalidades antigas.
5. Validar contas, câmera, dispositivos e Android individualmente; priorizar
   depois as partes do plano ainda ausentes (APK, painel de circuitos, etc.).

## Evidências locais

- logs/review-tests-20261114.log — main, 187 testes aprovados.
- logs/review-expansion-tests-20261114.log — primeira rodada, diferenças de ambiente.
- logs/review-expansion-isolated-20261114.log — 34 módulos isolados, sem timeouts.
- logs/review-expansion-normalized-20261114.log — 373 testes, uma falha de assets.

Esta é uma revisão de integração, cobertura e pontos críticos. Aprovação dos
testes não equivale a prova de ausência de defeitos em todos os fluxos.
