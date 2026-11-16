# Acesso remoto mobile — especificação

## Objetivo
Melhorar o uso do acesso remoto da JINX em celulares e permitir que um celular autorizado continue pareado após reinicializações do JINX, até o próprio celular sair ou o usuário revogar o pareamento.

## Experiência móvel
- Preservar o vocabulário visual escuro e índigo já usado pelo painel JINX; evoluir hierarquia, espaçamento e estados sem redesenhar as funções.
- Fazer a tela de entrada e o painel funcionar em larguras de celular, com altura dinâmica do navegador, áreas seguras e controles de toque de pelo menos 44 px.
- Corrigir a entrada manual: o servidor gera uma chave de 8 caracteres, portanto o campo deve aceitar e validar os 8 (não 6).
- Melhorar estados de conexão, reconexão, erro e carregamento. Erros transitórios de rede não devem apagar o pareamento local; somente rejeição definitiva ou saída/revogação deve removê-lo.
- Na entrada manual, oferecer “Manter este celular autorizado até sair ou revogar”, marcado por padrão, mas desmarcável para aparelhos compartilhados. O QR continua autorizando e lembrando o dispositivo como já sinaliza o fluxo atual.
- Melhorar o cabeçalho, feed e compositor de comandos em telas estreitas, sem remover envio de texto/arquivos, voz, ativação, status ou opções de sessão.

## Semântica de autorização
- “Permanente” significa confiança durável do dispositivo até logout local ou revogação, inclusive depois de reiniciar a JINX. Não significa token bearer sem expiração.
- Manter o TTL do token de sessão em 12 horas; o token durável do dispositivo permite solicitar outra sessão após fechar/reabrir o painel.
- Preservar os endpoints/rotas existentes e os fluxos QR e chave de uso único.
- Guardar no dispositivo servidor apenas o hash do token durável e a chave de sessão protegida em repouso. No Windows, usar DPAPI; em macOS/Linux, AES-GCM com chave em diretório privado do usuário (permissão 0600). A gravação será atômica.
- Arquivo ausente/corrompido deve falhar fechado: nenhuma autorização é concedida por registro ilegível e o arquivo existente não deve ser apagado automaticamente.
- Logout deste celular remove só seu pareamento; revogar todos remove os registros persistidos e invalida as sessões remotas atuais, mantendo a sessão que executou a revogação.
- Segredos e tokens não devem aparecer em logs.

## Direção visual
- Artifact: painel web remoto usado no celular.
- Público: proprietário da JINX operando um telefone já autorizado.
- Linguagem: interface utilitária escura/índigo da própria JINX, com foco claro no estado de conexão e no comando.
- Modo: redesign-preserve; varia apenas o layout responsivo e os estados de feedback.
- Dials: variância 2/10; movimento 1/10; densidade 6/10; dependência de assets 1/10; fidelidade à marca 9/10.
- Prioridade de viewport: celular em mão (aprox. 10 cm); hierarquia: conexão → conversa/comandos → controles auxiliares.
- Paleta existente: fundo `#07090f`, texto `#dde3ed`, acento `#6366f1`, verde `#22c55e`, neutros e bordas já definidos nas variáveis atuais.
- Tipografia: fonte de sistema existente; monoespaçada apenas para a chave de pareamento.
- Espaçamento: base 4 px, agrupamentos em múltiplos de 8 px; raio existente de 12–22 px.
- Movimento: feedback curto e reduzido; respeitar `prefers-reduced-motion`.

## Arquivos e testes
- `dashboard/device_store.py`: novo armazenamento de pareamentos com proteção por plataforma.
- `dashboard/server.py`: criação/consulta/remoção persistente; opção `remember` no login manual; persistência de QR, logout e revogação.
- `dashboard/static/login.html`: layout de entrada mobile, chave de 8 caracteres, opção lembrar, feedback acessível e reconexão que diferencia rejeição de falha de rede.
- `dashboard/static/app.html`: responsividade do painel autenticado, áreas seguras e controles táteis, preservando a navegação e as ações existentes.
- `tests/test_dashboard_remote_access.py`: cobertura de reinicialização, login manual lembrado/não lembrado, revogação, armazenamento protegido e estados de interface.
- `tests/test_remaining_implementation.py`: manter os contratos atuais do shell/PWA e da revogação.

## Critérios de aceite
1. Um login manual com a chave completa de 8 caracteres funciona; a opção de lembrar envia um token de dispositivo durável, e desmarcá-la não cria esse token.
2. Um dispositivo pareado por QR ou login lembrado consegue solicitar nova sessão após reconstruir o servidor usando o mesmo diretório de dados.
3. Logout e revogação de todos removem os registros persistidos; bearer tokens continuam expiráveis em 12 horas.
4. Um token bruto ou uma chave de sessão não aparece em texto aberto no arquivo de armazenamento.
5. A interface continua preservando rotas, funções, semântica, acessibilidade básica, PWA, voz, arquivos e controles existentes.
6. Testes de regressão direcionados e suíte completa passam.
