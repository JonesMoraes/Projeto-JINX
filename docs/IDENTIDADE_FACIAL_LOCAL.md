# Identidade facial local

O plugin `face_identity` reconhece pessoas usando YuNet + SFace pelo OpenCV. A
análise é feita na máquina: frames e recortes não são persistidos nem enviados a
modelos ou serviços externos. O SQLite guarda nomes, metadados, embeddings,
correções e horários de presença em `memory/face_identity.db`.

## Ativação e comandos

- `face_identity(action="start")`: inicia o reconhecimento e abre a webcam
  visível no HUD. A câmera não é ligada automaticamente.
- `face_identity(action="stop")`: interrompe o stream e apaga os tracks da sessão.
- `face_identity(action="enroll_photo", name="Maria", path="...")`: cadastra a
  melhor face de uma foto. Um diretório de fotos também é aceito (até 100 imagens).
- `face_identity(action="enroll_live", name="Maria")`: cadastra o track mais
  estável usando ao menos três amostras diversas já vistas pela webcam.
- `bootstrap_owner_photo` exige uma pasta com pelo menos dez amostras nítidas;
  `bootstrap_owner_live` usa a pessoa visível e marca o perfil como proprietário.
- `unknowns`, `name_unknown` e `merge_unknowns` listam, nomeiam retroativamente
  e mesclam grupos desconhecidos. `forget` remove a pessoa, embeddings e sightings.
- `correct` grava um exemplar negativo quando o track estável foi identificado
  incorretamente.

Para esquecer dados, use `face_identity(action="forget", name="Maria")`. A
remoção elimina cascata de exemplares, sightings e configurações do perfil.
Snapshots estão desativados; o caminho de imagem na base fica nulo.

## Modelos e limites desta versão

Os dois arquivos ONNX oficiais do OpenCV Zoo são baixados sob demanda para
`~/.jinx/models/faces/` e verificados por SHA-256 antes de carregar. YuNet usa
licença MIT e SFace Apache-2.0 conforme os READMEs de cada modelo
([YuNet](https://github.com/opencv/opencv_zoo/blob/main/models/face_detection_yunet/README.md),
[SFace](https://github.com/opencv/opencv_zoo/blob/main/models/face_recognition_sface/README.md)).
O threshold base 0.363 segue o exemplo oficial do OpenCV; depois do cadastro,
o valor é recalibrado usando os centroides das pessoas cadastradas e limitado
ao intervalo ±0.18 do threshold base.

Este primeiro corte usa CPU. CUDA, DirectML, CoreML, InsightFace, liveness,
OCR de rostos, RTSP/doorbells, galeria gráfica dedicada, exportação criptografada,
re-enrollment automático após trocar modelo e validação real de precisão em
três condições de iluminação ainda não estão implementados. Sem um conjunto de
validação consentido, não se pode afirmar a meta de 95% nem zero falsa aceitação.

Reconhecimento é somente contexto e personalização: nunca libera contas,
pagamentos, portas ou outras ações sensíveis. Para outras pessoas, cadastre
apenas com consentimento e cumpra as regras de privacidade aplicáveis, incluindo
a LGPD. O banco local não é criptografado nesta versão; proteja a conta do
sistema operacional e apague os registros quando não forem mais necessários.
