"""Bounded import/regression checks after human approval, before file replacement.

The temporary source copy contains no settings or user data. A subprocess is
not a security sandbox: approved Python still runs with the user's permissions.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

SOURCE_DIRS = {'actions', 'plugins', 'core', 'gui', 'providers', 'memory',
               'dashboard', 'tests'}
MAX_BYTES = 16 * 1024 * 1024
TIMEOUT = 20


def _run(stage: Path, program: str, args: list[str], log: Path) -> None:
    # Do not propagate API tokens supplied through the parent's environment.
    env = {key: value for key, value in os.environ.items() if key.upper() in {
        'SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP', 'COMSPEC',
        'SYSTEMDRIVE', 'PROGRAMFILES', 'PROGRAMFILES(X86)',
    }}
    env.update(QT_QPA_PLATFORM='offscreen', PYTHONIOENCODING='utf-8',
               PYTHONDONTWRITEBYTECODE='1', OPENBLAS_NUM_THREADS='1')
    try:
        # -I ignores PYTHONDONTWRITEBYTECODE, so -B is essential: same-sized
        # edits within one second must not reuse the baseline's cached bytecode.
        result = subprocess.run([sys.executable, '-I', '-B', '-X', 'utf8',
                                 '-c', program, str(stage, shell=False), *args],
                                cwd=stage, env=env, capture_output=True,
                                timeout=TIMEOUT)
    except subprocess.TimeoutExpired as exc:
        with log.open('ab') as output:
            output.write(b'\nRepair validation timed out\n')
            output.write((exc.stdout or b'')[-8000:] + (exc.stderr or b'')[-8000:])
        raise ValueError('Repair validation timed out; original file preserved') from None
    with log.open('ab') as output:
        output.write(b'\nRepair validation exit=' + str(result.returncode).encode() + b'\n')
        output.write(result.stdout[-8000:] + result.stderr[-8000:])
    if result.returncode:
        raise ValueError('Repair import/regression check failed; original file preserved. See repair-validation.log')


def validate(root: Path, relative: str, candidate: str, log: Path) -> str:
    root = root.resolve(strict=True)
    log.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    count = 0
    with tempfile.TemporaryDirectory(prefix='jinx-repair-check-') as folder:
        stage = Path(folder).resolve()
        # Explicit source roots only, never traverse a venv, assets or config.
        for name in sorted(SOURCE_DIRS):
            source = root / name
            if not source.is_dir() or source.is_symlink():
                continue
            for parent, dirs, files in os.walk(source, followlinks=False):
                dirs[:] = [d for d in dirs if d != '__pycache__'
                           and not (Path(parent) / d).is_symlink()]
                for filename in files:
                    path = Path(parent) / filename
                    if path.suffix != '.py' or path.is_symlink():
                        continue
                    rel = path.relative_to(root)
                    total += path.stat().st_size
                    count += 1
                    if total > MAX_BYTES or count > 1500:
                        raise ValueError('Repair source snapshot exceeds limits')
                    target = stage / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, target)
        for name in ('ui.py', 'main.py'):
            path = root / name
            if path.is_file() and not path.is_symlink():
                shutil.copyfile(path, stage / name)
        target = stage / relative
        if not target.is_file():
            raise ValueError('Repair target is not in the source snapshot')
        module = relative.removesuffix('.py').replace('/', '.')
        if module.endswith('.__init__'):
            module = module.removesuffix('.__init__')
        program = ('import sys,importlib; sys.path.insert(0,sys.argv[1]); '
                   'importlib.import_module(sys.argv[2])')
        # An already broken import cannot establish a reliable baseline here.
        # Leave that repair to the reviewed development workflow instead.
        _run(stage, program, [module], log)
        test = stage / 'tests' / ('test_' + Path(relative).stem + '.py')
        test_program = ('import sys,unittest; sys.path.insert(0,sys.argv[1]); '
                        'suite=unittest.defaultTestLoader.discover("tests",pattern=sys.argv[2]); '
                        'result=unittest.TextTestRunner(verbosity=2).run(suite); '
                        'sys.exit(0 if result.wasSuccessful() and result.testsRun else 1)')
        if test.is_file():
            _run(stage, test_program, [test.name], log)
        target.write_text(candidate, encoding='utf-8')
        _run(stage, program, [module], log)
        if test.is_file():
            _run(stage, test_program, [test.name], log)
        return 'import + ' + (test.name if test.is_file() else 'no dedicated tests available')
