"""Reviewable, isolated gesture runtime installation; never enables gestures."""
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import urllib.request
from urllib.parse import urlsplit
import os

from core.gesture_control import RUNTIME, PYTHON, MODEL, ROOT

MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task'
MANIFEST = Path(__file__).with_name('hand_runtime_windows_py312.json')


def base_python():
    if sys.version_info[:2] == (3, 12):
        return Path(sys.executable)
    candidate = Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs/Python/Python312/python.exe'
    if not candidate.is_file():
        raise RuntimeError('Mantenha Python 3.12 instalado para o runtime isolado de gestos.')
    return candidate


def prepare():
    # A pip dry-run can download entire wheels. Use a reviewed, hash-pinned
    # manifest instead, so preparation performs only small HEAD requests.
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    if sys.platform != manifest['platform']:
        raise RuntimeError('Runtime de gestos preparado para Windows/Python 3.12; outro ambiente requer novo plano.')
    base_python()
    packages = []
    for row in manifest['packages']:
        url = row['url']
        digest = row['sha256']
        if (urlsplit(url).scheme != 'https' or urlsplit(url).hostname != 'files.pythonhosted.org'
                or not re.fullmatch('[a-fA-F0-9]{64}', digest)):
            raise ValueError('Origem/hash de pacote inválido')
        with urllib.request.urlopen(urllib.request.Request(url, method='HEAD'), timeout=10) as reply:
            size = int(reply.headers.get('Content-Length', 0))
        if not 0 < size <= 150 * 1048576 or size != row['size']:
            raise ValueError('Tamanho de pacote não verificado')
        packages.append({'name': row['name'], 'url': url, 'sha256': digest, 'size': size})
    with urllib.request.urlopen(urllib.request.Request(MODEL_URL, method='HEAD'), timeout=10) as reply:
        size = int(reply.headers.get('Content-Length', 0))
        hashes = ','.join(reply.headers.get_all('x-goog-hash', []))
    md5 = next((part.strip()[4:] for part in hashes.split(',') if part.strip().startswith('md5=')), '')
    if (not md5 or not 0 < size < 20 * 1048576 or size != manifest['model_size']
            or md5 != manifest['model_md5']):
        raise ValueError('Tamanho/integridade do modelo não verificados')
    total = size + sum(p['size'] for p in packages)
    if not packages or total > 300 * 1048576:
        raise ValueError('Plano de gestos excede limites')
    return {'packages': packages, 'model_size': size, 'model_md5': md5, 'bytes': total}


def install(plan, *, approved=False):
    if approved is not True:
        return False, 'A instalação requer confirmação explícita do tamanho.'
    try:
        RUNTIME.mkdir(parents=True, exist_ok=True)
        logs = ROOT / 'logs'
        logs.mkdir(exist_ok=True)
        with (logs / 'gesture-install.log').open('ab') as log:
            subprocess.run([str(base_python()), '-m', 'venv', str(RUNTIME / 'env')],
                           stdout=log, stderr=subprocess.STDOUT, timeout=90, check=True, shell=False)
            artifacts = []
            for item in plan['packages']:
                if (urlsplit(item['url']).hostname != 'files.pythonhosted.org'
                        or urlsplit(item['url']).scheme != 'https'
                        or not re.fullmatch('[a-fA-F0-9]{64}', item['sha256'])):
                    raise ValueError('Invalid install plan')
                artifacts.append(item['url'] + '#sha256=' + item['sha256'])
            subprocess.run([str(PYTHON), '-m', 'pip', 'install', '--no-deps', *artifacts],
                           stdout=log, stderr=subprocess.STDOUT, timeout=300, check=True, shell=False)
            subprocess.run([str(PYTHON), '-m', 'pip', 'check'], stdout=log,
                           stderr=subprocess.STDOUT, timeout=30, check=True, shell=False)
            with urllib.request.urlopen(MODEL_URL, timeout=30) as reply:
                data = reply.read(20 * 1048576 + 1)
            if (len(data) != plan['model_size'] or
                    base64.b64encode(hashlib.md5(data).digest()).decode() != plan['model_md5']):
                raise ValueError('Hand model checksum mismatch')
            temp = MODEL.with_suffix('.download')
            temp.write_bytes(data)
            temp.replace(MODEL)
            # Verify actual model construction; no camera or mouse is opened.
            program = ('import mediapipe as mp,sys; '
                'v=mp.tasks.vision; '
                'd=v.HandLandmarker.create_from_options(v.HandLandmarkerOptions('
                'base_options=mp.tasks.BaseOptions(model_asset_path=sys.argv[1]),num_hands=1)); '
                'd.close(); print("Hand model OK")')
            subprocess.run([str(PYTHON, shell=False), '-I', '-c', program, str(MODEL)], stdout=log,
                           stderr=subprocess.STDOUT, timeout=45, check=True, shell=False)
        (RUNTIME / 'ready.json').write_text(json.dumps({'sha256': hashlib.sha256(data).hexdigest(),
                                                     'bytes': plan['bytes']}), encoding='utf-8')
        return True, 'Gestos instalados e modelo verificado. Controle continua desligado; ative explicitamente com F10.'
    except Exception as exc:
        return False, 'Instalação de gestos não concluída: ' + type(exc).__name__ + '. Veja logs/gesture-install.log.'
