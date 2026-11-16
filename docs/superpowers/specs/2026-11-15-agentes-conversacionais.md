# Especificação: agentes conversacionais na JINX

**Status:** proposta para revisão; nenhum código desta funcionalidade foi alterado.

## Problema

A JINX tem uma identidade conversacional principal e agentes de tarefas em `agents/*.md`. Esses agentes Markdown pertencem ao executor de tarefas e não são personas selecionáveis durante a conversa por voz. O usuário quer criar nomes como AFONSO, chamar uma persona específica e permitir que duas personas conversem sobre um tema.

## Terminologia

- **JINX principal:** a assistente de voz já existente, com ferramentas e sessão Live atuais.
- **Perfil conversacional:** nome e instruções de uma persona secundária, configuráveis pela interface. É separado dos perfis Markdown de tarefas.
- **Consulta direcionada:** uma chamada pontual a um perfil, iniciada explicitamente pelo usuário, por exemplo: “Afonso, explique este assunto”.
- **Diálogo:** geração alternada e limitada entre dois perfis, sobre um tema dado pelo usuário.

## Escopo do MVP proposto

1. Em Configurações, permitir criar, editar e remover perfis conversacionais com nome único, instruções de persona e modo de geração Rápido/Análise.
2. Salvar os perfis localmente junto às configurações existentes, sem solicitar ou duplicar credenciais. O nome atual da JINX representa o perfil principal e não pode ser removido.
3. Disponibilizar uma ferramenta de consulta que a JINX possa acionar quando o usuário chamar outro perfil pelo nome. A resposta será atribuída ao perfil chamado; a sessão de voz atual da JINX fará a leitura com sua voz configurada.
4. Disponibilizar uma ferramenta de diálogo para dois perfis escolhidos, incluindo o perfil principal. O padrão será duas rodadas; o limite rígido será três rodadas por perfil. O resultado será rotulado por nome e devolvido à conversa atual.
5. Os perfis secundários usarão a escada de modelos/provedor já configurada para chamadas de texto da JINX. Cada perfil poderá escolher Rápido ou Análise, mas não terá provedor, credencial nem voz independente nesta versão.
6. Chamadas dos perfis serão somente texto: não terão acesso a ferramentas, arquivos, navegador, microfone, rede ou ações da máquina. Somente o usuário pode iniciar uma consulta ou diálogo; não haverá conversa em segundo plano.
7. Respostas dos perfis serão tratadas como conteúdo citado e não confiável pela persona seguinte e pela JINX principal. Falhas de modelo serão reportadas sem fabricar resposta.
8. Os agentes existentes em `agents/*.md` e o executor `core/tasks` permanecerão inalterados.

## Fora de escopo

- Voz diferente por agente; o áudio continuará usando a voz atual da JINX.
- Chaves, provedores e modelos independentes por perfil.
- Atribuição autônoma de tarefas ou chamadas não solicitadas.
- Dar ferramentas, permissões de sistema ou acesso à rede aos perfis secundários.
- Substituir ou migrar os agentes Markdown já existentes.

## Critérios de aceite

- É possível salvar AFONSO com instruções próprias, reiniciar a aplicação e encontrá-lo ainda configurado.
- Ao chamar um perfil existente, a ferramenta usa suas instruções e nível Rápido/Análise, e devolve resposta atribuída ao nome correto.
- Perfil inexistente, nome duplicado, nome vazio, instrução vazia, pergunta vazia e falha do provedor resultam em erro controlado, sem chamada inválida ou resposta inventada.
- Dois perfis alternam respostas sobre o tema informado, com rótulos, duas rodadas por padrão e nunca mais de três.
- A saída de um agente não se transforma em solicitação de ferramenta, ação externa ou alteração de configuração para o outro agente.
- A interface permite adicionar, editar e remover perfis secundários sem alterar credenciais, identidade, temas ou preferências existentes.
- A suíte existente continua passando.

## Decisões que o usuário deve confirmar

O MVP pressupõe o mesmo provedor/modelo de texto e a mesma voz da JINX, com diferença de comportamento por instruções e nome. Se o usuário quiser vozes ou provedores independentes por perfil desde o início, o escopo deve ser atualizado antes da implementação.