# Python no Windows

Política solicitada em 14/11/2026: usar a versão estável mais recente do
CPython. Na implantação desta política, python.org publica 3.15.2. Requisito
do aplicativo: Python >=3.15, registrado em setup.py; .python-version aponta
para 3.15.2. requirements.txt lista os pacotes, não o interpretador: pip não
instala o próprio Python como uma dependência comum.

Abra por INICIAR_JINX.cmd. runtime_manager.py consulta a indicação oficial de
versão estável no python.org a cada abertura, sem selecionar alpha/beta/RC.
Se houver atualização, verifica SHA-256 e assinatura Authenticode do instalador,
atualiza o Python por usuário e cria um ambiente separado em
.jinx_runtime/envs/<versão>. Instala requirements, executa pip check e a suíte
unittest antes de selecionar esse ambiente para iniciar main.py. Extras
leves já instalados (PDF, loopback/vozes) são preservados quando
compatíveis; isso não habilita novos recursos opcionais.
Navegadores Playwright também são preparados. O primeiro preparo pode levar alguns minutos.

A seleção só muda após aprovação dos testes. Se faltar rede ou uma dependência
não suportar o novo Python, o inicializador informa a falha e mantém o ambiente
anterior disponível; nessa condição não é possível garantir a versão mais
recente. Logs: logs/python-runtime.log, logs/python-installer.log e
logs/desktop-start.log. Instalações futuras podem baixar pacotes novamente.
Use sempre o .cmd para aplicar a política; executar .venv/Scripts/python.exe
main.py diretamente continua usando o ambiente antigo explicitamente escolhido.
Novos atalhos e novas ativações de início automático criados pelo JINX usam
launch_jinx.pyw, que aplica a mesma política sem console. Atalhos antigos que
apontam diretamente para main.py precisam ser recriados pela interface.

Python 3.12 e .venv não são removidos. O suporte opcional de gestos tem
runtime próprio 3.12 e continuará assim enquanto o seu modelo/dependências
forem preparados para essa versão; isso não limita o Python principal.
Atualizar Python não instala automaticamente o runtime de gestos ainda pendente.

Quando não existe wheel de PyYAML para o Python novo, o instalador usa a
variante Python pura suportada pelo pacote, sem instalar compiladores C++.
Referência: https://github.com/yaml/pyyaml/blob/6.0.3/setup.py.

Fonte: https://www.python.org/downloads/windows/ e
https://www.python.org/downloads/release/python-3152/.

## Validação desta implantação

- Python 3.15.2 instalado por usuário; instalador oficial com SHA-256 e
  assinatura Python Software Foundation verificados. Instalação Windows terminou
  com código 0, sem reinício.
- Ambiente .jinx_runtime/envs/3.15.2 com requirements, pypdf e SoundCard
  previamente presentes. pip check sem conflitos.
- 411 testes passaram no Python 3.15.2, sem skips, em 39,69 s.
- JINX iniciado pelo launch_jinx.pyw: processo main.py do ambiente 3.15.2,
  sessão de voz conectada, microfone/recepção/reprodução iniciados nos logs.
  Isso não representa uma nova confirmação humana de escuta ou conversa.
- Estado de seleção local em .jinx_runtime/current.json; logs de instalação,
  testes e execução em logs/. Configurações pessoais não foram reescritas.
