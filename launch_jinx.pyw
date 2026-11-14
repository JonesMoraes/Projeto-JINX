"""Console-free Windows shortcut entry; always uses the verified runtime policy."""
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import sys


if __name__ == '__main__':
    root = Path(__file__).resolve().parent
    (root / 'logs').mkdir(exist_ok=True)
    with (root / 'logs' / 'runtime-launch.log').open('a', encoding='utf-8') as log:
        with redirect_stdout(log), redirect_stderr(log):
            import runtime_manager
            sys.argv = [str(root / 'runtime_manager.py'), '--launch']
            result = runtime_manager.main()
    raise SystemExit(result)
