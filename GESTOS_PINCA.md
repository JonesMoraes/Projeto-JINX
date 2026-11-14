# Controle local por pinça

Implementação de 14/11/2026. Inicialmente desligada. Windows, tela principal,
uma mão, webcam existente do JINX. Não grava imagens nem usa um modelo remoto.

## Uso

1. Instale o suporte em Configurações → Configurações dos plugins → GESTOS /
   PINÇA. O instalador mostra o tamanho e exige confirmação antes de instalar.
2. Deixe a webcam apontada para a mão, com boa iluminação. Saia do modo orb
   com F11 e deixe o JINX ao lado do Explorador de Arquivos para ver o alvo.
3. Pressione F10 no JINX ou use Configurações → CONTROLE POR GESTOS [F10].
   Também aceita pedido explícito por voz: “ative o controle por gestos”.
4. Abra polegar e indicador por um instante para armar. O indicador move o
   cursor com espelhamento horizontal e suavização.
5. Sobre o alvo, una polegar e indicador e mantenha a pinça por cerca de
   0,18 s para segurar o botão esquerdo. Mova a mão para arrastar; abra a pinça
   para soltar. Um ciclo curto de segurar/soltar equivale a um clique.
6. Esc/F10 interrompem o controle, inclusive com outro aplicativo em foco
   no Windows. O botão PARAR também fica visível enquanto gestos estão ativos.
   F9 desliga a câmera e encerra os observadores. Fechar o JINX solta o mouse.

Ao perder a mão, o botão esquerdo é solto na posição atual; isso pode soltar
um arquivo no local em que ele estiver. Abra a pinça novamente para rearmar.
Teste primeiro com uma janela ou arquivo descartável. Gestos emulam o mouse:
não identificam arquivos, não escolhem destinos e não fazem uma movimentação
semântica verificada pelo sistema de arquivos. Não há zoom/rotação 3D nesta versão.

## Dependências e instalação

Plano consultado nesta máquina: 95,8 MiB (aproximadamente 100 MB decimais),
incluindo modelo de 7,5 MiB e 19 pacotes. Espaço em disco após descompactar é
maior que o download. As versões/fontes/hashes estão no plano local em logs/.
O tamanho é recalculado pelo instalador para a máquina em que for usado.

MediaPipe 0.10.35, NumPy <3 e OpenCV contrib <5 ficam em um ambiente próprio em
config/gesture_runtime/env. O ambiente Python principal e requirements.txt
não mudam. O modelo oficial Hand Landmarker é armazenado no mesmo diretório.
Nada é instalado, baixado ou ativado simplesmente por abrir o aplicativo.

Instalação real ainda exige a aprovação específica do download acima de 20 MB,
conforme o plano do projeto. O instalador oferece revisão pelo HUD; mesmo após
instalar, não abre a webcam nem ativa o mouse automaticamente.

## Funcionamento e validação

- Reaproveita a única captura de câmera do aplicativo. A thread de câmera
  entrega apenas o frame mais recente, reduzido para 480×270, a um processo
  local separado; esse processo devolve somente coordenadas dos dedos.
- Não importa MediaPipe no boot principal, não executa ML na thread Qt e não
  cria widgets em plugins. Eventos de UI passam pelos sinais de MainWindow.
- Pinça usa distância relativa à largura da palma, limiares distintos para
  fechar/abrir, tempo mínimo e exigência de abertura inicial. Não arma quando
  a câmera já encontra a mão fechada.
- Watchdog independente solta o mouse após 0,5 s sem resultado recente e
  encerra um detector sem resposta. Resultados com mais de 0,4 s não movem
  o cursor. Cada início usa um novo processo e começa desarmado.
- Esc/F10 globais são lidos por GetAsyncKeyState. Injeção de mouse usa as
  APIs Windows existentes; janelas protegidas/elevadas podem recusar entrada.
- Testes de armar, segurar, arrastar, soltar, oscilação, perda de mão,
  emergência, timeout, dependência ausente, confirmação e indicador de UI
  usam coordenadas/mouse simulados. Nenhum arquivo pessoal foi arrastado.
- Primeira suíte integrada: 404 testes passaram. Reconhecimento físico,
  qualidade de rastreamento e latência real dependem da instalação e do teste
  da câmera/mão do usuário; não são comprovados pelos testes simulados.

Referência técnica e origem do modelo:
[Google AI Edge — Hand Landmarker para Python](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker?tab=Python).
A integração foi escrita para os requisitos do JINX; nenhum código de outra
aplicação de assistente foi incorporado.
