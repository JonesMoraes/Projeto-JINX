"""Image generation through the shared core, displayed with the existing Qt signal."""
import io
import uuid
from pathlib import Path
from core import gemini, outcome
from core.plugin_jobs import Jobs
from memory.config_manager import get_base_dir

PLUGIN = {'name': 'generate_image', 'description': 'Gerar imagem / Generate an image with configured cloud image models. May consume API quota. Saved locally and displayed in HUD.',
    'parameters': {'type': 'OBJECT', 'properties': {'prompt': {'type': 'STRING'},
    'action': {'type': 'STRING', 'enum': ['generate', 'status']}}, 'required': ['action']}}
PLUGIN_SETTINGS = {'namespace': 'image_generation', 'title': 'IMAGENS / IMAGES — API', 'fields': [
    {'key': 'enabled', 'label': 'Ativar geração (consome API) / Enable generation (API usage)', 'type': 'toggle', 'default': False},
    {'key': 'models', 'label': 'Modelos de imagem, separados por vírgula / Image models, comma separated', 'type': 'text'}]}
_jobs = Jobs('Imagem / Image')


def _generate(prompt, player):
    result = gemini.generate_image(prompt)
    if not result:
        return outcome.failed('generate_image', 'Nenhuma imagem retornada; confira modelos e cota / No image returned; check models and quota')
    data, mime = result
    from PIL import Image
    with Image.open(io.BytesIO(data)) as img:
        if img.width * img.height > 25000000:
            return outcome.failed('generate_image', 'Imagem grande demais / Image too large')
        img.verify()
    folder = Path(get_base_dir()) / 'generated' / 'images'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (uuid.uuid4().hex + {'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp'}[mime])
    with path.open('xb') as handle:
        handle.write(data)
    if path.read_bytes() != data:
        return outcome.unverified('generate_image', 'Falha na verificação do arquivo / File verification failed')
    try:
        if player:
            player.show_image(str(path), 'Imagem gerada / Generated image')
    except Exception:
        pass
    return outcome.done('generate_image', path=str(path))


def run(parameters, player=None, session_memory=None):
    try:
        if parameters.get('action') == 'status':
            return _jobs.last
        prompt = parameters.get('prompt')
        if parameters.get('action') != 'generate' or not isinstance(prompt, str) or not prompt.strip():
            return outcome.failed('generate_image', 'Informe a descrição / Provide a prompt')
        return _jobs.start(lambda: _generate(prompt, player), player)
    except Exception:
        return outcome.failed('generate_image', 'Parâmetros inválidos / Invalid parameters')
