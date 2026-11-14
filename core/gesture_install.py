"""Reviewable, isolated gesture runtime installation; never enables gestures."""
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.request
from urllib.parse import urlsplit
import venv

from core.gesture_control import RUNTIME, PYTHON, MODEL, ROOT

MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task'
SPECS = ('mediapipe==0.10.35', 'opencv-contrib-python>=4.8,<5', 'numpy>=1.24,<3')


def prepare(report_path=None):
    with tempfile.TemporaryDirectory(prefix='jinx-hand-plan-') as folder:
        report = Path(folder) / 'packages.json'
        if report_path is None:
            result = subprocess.run([sys.executable, '-m', 'pip', 'install', '--dry-run',
                '--ignore-installed', '--only-binary=:all:', '--report', str(report), *SPECS],
                capture_output=True, timeout=120)
            if result.returncode:
                raise RuntimeError('Plano do MediaPipe indisponível')
        else:
            report = Path(report_path)
        packages = []
        for row in json.loads(report.read_text(encoding='utf-8'))['install']:
            info = row['download_info']
            url = info['url']
            digest = info.get('archive_info', {}).get('hashes', {}).get('sha256', '')
            if (urlsplit(url).scheme != 'https' or urlsplit(url).hostname != 'files.pythonhosted.org'
                    or not re.fullmatch('[a-fA-F0-9]{64}', digest)):
                raise ValueError('Origem/hash de pacote inválido')
            with urllib.request.urlopen(urllib.request.Request(url, method='HEAD'), timeout=10) as reply:
                size = int(reply.headers.get('Content-Length', 0))
            if not 0 < size <= 150 * 1048576:
                raise ValueError('Tamanho de pacote não verificado')
            packages.append({'name': row['metadata']['name'], 'url': url, 'sha256': digest, 'size': size})
        with urllib.request.urlopen(urllib.request.Request(MODEL_URL, method='HEAD'), timeout=10) as reply:
            size = int(reply.headers.get('Content-Length', 0))
            hashes = ','.join(reply.headers.get_all('x-goog-hash', []))
        md5 = next((part.strip()[4:] for part in hashes.split(',') if part.strip().startswith('md5=')), '')
        if not md5 or not 0 < size < 20 * 1048576:
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
            venv.EnvBuilder(with_pip=True).create(RUNTIME / 'env')
            artifacts = []
            for item in plan['packages']:
                if (urlsplit(item['url']).hostname != 'files.pythonhosted.org'
                        or urlsplit(item['url']).scheme != 'https'
                        or not re.fullmatch('[a-fA-F0-9]{64}', item['sha256'])):
                    raise ValueError('Invalid install plan')
                artifacts.append(item['url'] + '#sha256=' + item['sha256'])
            subprocess.run([str(PYTHON), '-m', 'pip', 'install', '--no-deps', *artifacts],
                           stdout=log, stderr=subprocess.STDOUT, timeout=300, check=True)
            subprocess.run([str(PYTHON), '-m', 'pip', 'check'], stdout=log,
                           stderr=subprocess.STDOUT, timeout=30, check=True)
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
            subprocess.run([str(PYTHON), '-I', '-c', program, str(MODEL)], stdout=log,
                           stderr=subprocess.STDOUT, timeout=45, check=True)
        (RUNTIME / 'ready.json').write_text(json.dumps({'sha256': hashlib.sha256(data).hexdigest(),
                                                     'bytes': plan['bytes']}), encoding='utf-8')
        return True, 'Gestos instalados e modelo verificado. Controle continua desligado; ative explicitamente com F10.'
    except Exception as exc:
        return False, 'Instalação de gestos não concluída: ' + type(exc).__name__ + '. Veja logs/gesture-install.log.'
