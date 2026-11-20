# Python no Windows

Política revisada em 19/11/2026: fixar o Python em **3.12** em vez de 3.14,
para que o aplicativo inteiro — e não só o runtime isolado de gestos — rode
em **um único interpretador**. O 3.12 é a interseção que todas as
dependências suportam com wheels publicados, inclusive o mediapipe dos
gestos, cujos wheels param no 3.12. Exemplos verificados nesta migração:
onnxruntime/openwakeword (wake word), PyQt6 6.11 (wheels abi3), sounddevice,
google-genai, piper-tts, faster-whisper, pandas, vosk e pydub (que no 3.12
usa o `audioop` da biblioteca padrão — sem necessidade do audioop-lts).
Requisito do aplicativo: Python >=3.12, registrado em setup.py;
.python-version aponta para 3.12.10 e é ele que decide o major.minor.
requirements.txt lista os pacotes, não o interpretador: pip não instala o
próprio Python como uma dependência comum.

# Histórico — política de 14/11/2026 (fixar em 3.14)

Política revisada em 14/11/2026: fixar o Python em **3.14** em vez de
acompanhar a última estável. Requisito do aplicativo: Python >=3.14, registrado
em setup.py; .python-version aponta para 3.14.10 e é ele que decide o
major.minor. requirements.txt lista os pacotes, não o interpretador: pip não
instala o próprio Python como uma dependência comum.

A mudança tem uma razão medida. Sob 3.15 a instalação inteira funcionava, mas o
wake word ("Hey Jarvis") não: openwakeword exige onnxruntime, e nenhuma versão
do onnxruntime publica wheel cp315 (a 1.32.0 para em cp314, e não há abi3). Sob
3.14 os 417 testes passam e o próprio wake word carrega o modelo. O mediapipe
dos gestos continua exigindo 3.12, em runtime separado — igual nas duas.

Abra por INICIAR_JINX.cmd. runtime_manager.py lê .python-version e escolhe a
última revisão daquele major.minor que tenha instalador Windows (releases
somente-de-segurança publicam apenas código-fonte e são puladas), sem
selecionar alpha/beta/RC. O .cmd continua chamando `py -3`: ele só inicia o
gerenciador, que é stdlib puro e então monta o ambiente da versão fixada.
Se houver atualização de patch, verifica SHA-256 e assinatura Authenticode do
instalador, atualiza o Python por usuário e cria um ambiente separado em
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

Fonte: https://www.python.org/downloads/windows/, https://www.python.org/ftp/python/ e
https://www.python.org/downloads/release/python-31410/.

## Validação desta implantação

- Python 3.14.10 instalado por usuário; o 3.15.2 permanece na máquina apenas
  como bootstrap e não é mais selecionado.
- Ambiente .jinx_runtime/envs/3.14.10 com requirements instalados, pip check
  sem conflitos e 417 testes aprovados (1 skip: pypdf opcional).
- openwakeword 0.6.0 + onnxruntime instalados; modelo hey_jarvis baixado e
  carregado, predict respondendo sem erro.
- JINX iniciado pelo launch_jinx.pyw: processo main.py do ambiente 3.14.10,
  sessão de voz conectada, microfone/recepção/reprodução iniciados nos logs.
  Isso não representa uma nova confirmação humana de escuta ou conversa.
- Python 3.12.10 instalado por usuário para o runtime isolado de gestos.
- Estado de seleção local em .jinx_runtime/current.json; logs de instalação,
  testes e execução em logs/. Configurações pessoais não foram reescritas.
