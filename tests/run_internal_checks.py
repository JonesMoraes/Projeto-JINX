r"""Run each test module in isolation with a deadline and durable local results.

Usage: .venv-local\Scripts\python.exe tests/run_internal_checks.py
No credentials, network permission or hardware validation is implied by passing.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def probe_asyncio(timeout=5):
    """Check the runtime, with no application imports or patched event loop."""
    command = [sys.executable, '-u', '-c',
               'import asyncio,faulthandler,sys; '
               'from core.voice_runtime import prerequisite_problem; '
               'problem = prerequisite_problem(); '
               'print(problem or "Local runtime prerequisite OK", flush=True); '
               'sys.exit(2) if problem else None; '
               'faulthandler.dump_traceback_later(3, exit=True); '
               'asyncio.run(asyncio.sleep(0)); print("asyncio OK")']
    try:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=timeout)
        return {'state': 'passed' if result.returncode == 0 else 'blocked',
                'output': result.stdout + result.stderr}
    except subprocess.TimeoutExpired:
        return {'state': 'blocked', 'output': 'Event loop preflight exceeded its deadline.'}


def check(path, timeout):
    started = time.monotonic()
    command = [sys.executable, '-u', '-m', 'unittest', 'discover', '-s', 'tests', '-p', path.name, '-v']
    try:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=timeout,
                                env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen',
                                     'PYTHONIOENCODING': 'utf-8'})
        state = 'passed' if result.returncode == 0 else 'failed'
        output = result.stdout + result.stderr
        code = result.returncode
    except subprocess.TimeoutExpired as exc:
        state, code = 'timeout', None
        def decode(value):
            return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else (value or '')
        output = decode(exc.stdout) + decode(exc.stderr)
    return {'module': path.name, 'state': state, 'exit_code': code,
            'seconds': round(time.monotonic() - started, 2), 'output': output}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--timeout', type=int, default=30)
    parser.add_argument('--run-despite-preflight', action='store_true',
                        help='Run all tests even if the unmodified asyncio runtime is blocked.')
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error('timeout must be positive')
    results = []
    folder = ROOT / 'logs' / 'internal_checks'
    folder.mkdir(parents=True, exist_ok=True)
    probe = probe_asyncio()
    (folder / 'environment.json').write_text(json.dumps(probe, indent=2), encoding='utf-8')
    if probe['state'] != 'passed':
        print('BLOCKED: Python asyncio cannot start in this executor. See environment.json.', flush=True)
        if not args.run_despite_preflight:
            # Preserve earlier module results; this is no test pass or failure.
            return 2
    # Sequential modules avoid cross-process interference with existing fixtures.
    for path in sorted((ROOT / 'tests').glob('test_*.py')):
        row = check(path, args.timeout)
        (folder / (path.stem + '.log')).write_text(row.pop('output'), encoding='utf-8')
        results.append(row)
        (folder / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        print(f"{row['state']}: {row['module']} ({row['seconds']}s)", flush=True)
    counts = {state: sum(r['state'] == state for r in results) for state in ('passed', 'failed', 'timeout')}
    print(json.dumps(counts), flush=True)
    return 0 if all(r['state'] == 'passed' for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
