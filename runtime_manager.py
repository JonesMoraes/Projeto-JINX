"""Windows stable-Python updater and verified application launcher (stdlib only)."""
import argparse
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parent
STATE = ROOT / '.jinx_runtime'
CURRENT = STATE / 'current.json'


class FileRows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = None

    def handle_starttag(self, tag, attrs):
        if tag == 'tr': self.row = {'links': [], 'text': ''}
        if tag == 'a' and self.row is not None:
            self.row['links'].append(dict(attrs).get('href', ''))

    def handle_data(self, data):
        if self.row is not None: self.row['text'] += data

    def handle_endtag(self, tag):
        if tag == 'tr' and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def fetch(url, limit=2_000_000):
    with urllib.request.urlopen(url, timeout=15) as response:
        data = response.read(limit + 1)
    if len(data) > limit: raise ValueError('Download exceeds limit')
    return data


def release(version):
    """(version, installer URL, SHA-256) for one exact release, from python.org."""
    url = f'https://www.python.org/ftp/python/{version}/python-{version}-amd64.exe'
    page = 'https://www.python.org/downloads/release/python-' + version.replace('.', '') + '/'
    parser = FileRows()
    parser.feed(fetch(page).decode())
    for row in parser.rows:
        if url in row['links']:
            digest = re.search(r'(?<![a-f0-9])[a-f0-9]{64}(?![a-f0-9])', re.sub(r'\s+', '', row['text']))
            if digest: return version, url, digest[0]
    raise ValueError('Installer SHA-256 missing from official release page')


def latest():
    """The newest stable CPython python.org advertises, wherever it is."""
    html = fetch('https://www.python.org/downloads/windows/').decode()
    match = re.search(r'Latest Python 3 Release\s*-\s*Python (3\.\d+\.\d+)', html)
    if not match: raise ValueError('Latest stable Python not found')
    return release(match[1])


def pinned():
    """The major.minor this project runs on, from .python-version; None if unset."""
    try:
        text = (ROOT / '.python-version').read_text(encoding='utf-8').strip()
    except OSError:
        return None
    match = re.match(r'(\d+)\.(\d+)', text)
    return (int(match[1]), int(match[2])) if match else None


def target():
    """The release to run: the pinned minor when .python-version names one.

    Chasing the newest stable on every launch is what turns a working install
    into a broken one: a brand-new CPython lands each October and the native
    packages (onnxruntime, mediapipe) take months to publish a wheel for it.
    The pin decides the major.minor; patches inside it still move forward.
    Security-only releases publish no Windows installer, so patches are tried
    newest-first until one actually has one.
    """
    minor = pinned()
    if minor is None:
        return latest()
    index = fetch('https://www.python.org/ftp/python/').decode()
    patches = sorted({(int(a), int(b), int(c)) for a, b, c in
                      re.findall(r'(?<![\d.])(\d+)\.(\d+)\.(\d+)/', index)
                      if (int(a), int(b)) == minor}, reverse=True)
    if not patches:
        raise ValueError(f'python.org publishes no {minor[0]}.{minor[1]} release')
    for patch in patches[:5]:
        try:
            return release('.'.join(map(str, patch)))
        except ValueError:
            continue   # source-only release: no Windows installer to verify
    raise ValueError(f'No Windows installer published for Python {minor[0]}.{minor[1]}')


def run(args, log, timeout=1200, **kwargs):
    result = subprocess.run([str(a) for a in args], stdout=log, stderr=subprocess.STDOUT,
                            timeout=timeout, **kwargs)
    if result.returncode not in (0, 3010):
        raise RuntimeError(f'Command failed ({result.returncode}); see logs/python-runtime.log')


def version_of(executable):
    result = subprocess.run([str(executable), '-I', '-c',
        'import sys; print(".".join(map(str,sys.version_info[:3])))'],
        capture_output=True, text=True, timeout=15, check=True)
    return result.stdout.strip()


def installed_extras():
    source = ROOT / '.venv' / 'Scripts' / 'python.exe'
    if CURRENT.is_file():
        row = json.loads(CURRENT.read_text(encoding='utf-8'))
        candidate = (STATE / row['python']).resolve()
        if STATE.resolve() in candidate.parents and candidate.is_file(): source = candidate
    if not source.is_file(): return []
    specs = {'pypdf': 'pypdf>=7,<8', 'SoundCard': 'SoundCard>=0.4,<1',
             'edge-tts': 'edge-tts', 'miniaudio': 'miniaudio', 'soundfile': 'soundfile'}
    program = ('import importlib.metadata as m,json; '
               'print(json.dumps([d.metadata["Name"].lower() for d in m.distributions()]))')
    result = subprocess.run([str(source), '-I', '-c', program], capture_output=True,
                            text=True, check=True, timeout=30)
    names = set(json.loads(result.stdout))
    return [spec for name, spec in specs.items() if name.lower() in names]


def prepare(version, url, digest, log):
    extras = installed_extras()
    major, minor, _ = map(int, version.split('.'))
    base = Path(os.environ['LOCALAPPDATA']) / 'Programs' / 'Python' / f'Python{major}{minor}' / 'python.exe'
    if not base.is_file() or version_of(base) != version:
        target = STATE / 'downloads' / f'python-{version}-amd64.exe'
        target.parent.mkdir(parents=True, exist_ok=True)
        data = target.read_bytes() if target.is_file() else fetch(url, limit=80 * 1048576)
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('Python installer checksum mismatch')
        target.write_bytes(data)
        # Verify Authenticode as well as the checksum from python.org.
        script = "$s=Get-AuthenticodeSignature -LiteralPath '" + str(target).replace("'", "''") + "'; if ($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notlike '*Python Software Foundation*') { exit 1 }"
        signature_env = dict(os.environ)
        # PowerShell 7 module paths cannot be inherited by Windows PowerShell 5.
        signature_env.pop('PSModulePath', None)
        run([shutil.which('pwsh') or 'powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script], log,
            timeout=30, env=signature_env)
        run([target, '/quiet', 'InstallAllUsers=0', 'PrependPath=0', 'Include_launcher=0',
             'Include_test=0', '/log', ROOT / 'logs' / 'python-installer.log'], log, timeout=900)
    if version_of(base) != version:
        raise RuntimeError('Installed Python version was not confirmed')
    folder = STATE / 'envs' / version
    python = folder / 'Scripts' / 'python.exe'
    if not python.is_file() or version_of(python) != version:
        run([base, '-m', 'venv', folder], log)
    # PyYAML's optional C extension may lack a wheel on a new CPython.
    # Its upstream-supported pure-Python build avoids requiring MSVC.
    build_env = dict(os.environ, PYYAML_FORCE_LIBYAML='0')
    run([python, '-m', 'pip', 'install', '-r', ROOT / 'requirements.txt'], log, env=build_env)
    if extras: run([python, '-m', 'pip', 'install', *extras], log)
    run([python, '-m', 'pip', 'check'], log)
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen', PYTHONIOENCODING='utf-8')
    # Use canonical temporary paths even when Windows exposes an 8.3 alias.
    import tempfile
    env['TEMP'] = env['TMP'] = str(Path(tempfile.gettempdir()).resolve())
    run([python, '-m', 'unittest', 'discover', '-s', 'tests', '-v'], log,
        timeout=240, cwd=ROOT, env=env)
    run([python, '-m', 'playwright', 'install', 'chromium', 'firefox'], log, timeout=300)
    return python


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--launch', action='store_true')
    args = parser.parse_args()
    if sys.platform != 'win32': raise RuntimeError('Runtime updater supports Windows only')
    (ROOT / 'logs').mkdir(exist_ok=True)
    STATE.mkdir(exist_ok=True)
    selected = None
    if CURRENT.is_file():
        row = json.loads(CURRENT.read_text(encoding='utf-8'))
        candidate = (STATE / row['python']).resolve()
        if STATE.resolve() in candidate.parents and candidate.is_file(): selected = candidate
    try:
        version, url, digest = target()
        print(f'Python estavel atual: {version}', flush=True)
        if selected is None or version_of(selected) != version:
            print('Preparando e testando o novo ambiente. Progresso: logs/python-runtime.log', flush=True)
            import msvcrt
            with (STATE / 'update.lock').open('a+b') as guard:
                if guard.tell() == 0: guard.write(b'0'); guard.flush()
                guard.seek(0)
                msvcrt.locking(guard.fileno(), msvcrt.LK_NBLCK, 1)
                try:
                    with (ROOT / 'logs' / 'python-runtime.log').open('ab') as log:
                        selected_new = prepare(version, url, digest, log)
                finally:
                    guard.seek(0)
                    msvcrt.locking(guard.fileno(), msvcrt.LK_UNLCK, 1)
            record = {'version': version, 'python': selected_new.relative_to(STATE).as_posix()}
            temporary = CURRENT.with_suffix('.tmp')
            temporary.write_text(json.dumps(record), encoding='utf-8')
            os.replace(temporary, CURRENT)
            selected = selected_new
            print(f'Python {version} validado e selecionado.', flush=True)
    except Exception as exc:
        print(f'Atualizacao nao concluida: {type(exc).__name__}: {exc}', flush=True)
        if selected is None:
            # Keep the known working environment available, never silently use system Python.
            fallback = ROOT / '.venv' / 'Scripts' / 'python.exe'
            if not args.launch or not fallback.is_file(): return 1
            selected = fallback
        print('Usando o ambiente anterior; a versao mais recente nao foi validada.', flush=True)
        if not args.launch: return 1
    if args.launch:
        with (ROOT / 'logs' / 'desktop-start.log').open('ab') as log:
            return subprocess.call([str(selected), '-u', str(ROOT / 'main.py')], cwd=ROOT,
                                   stdout=log, stderr=subprocess.STDOUT)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
