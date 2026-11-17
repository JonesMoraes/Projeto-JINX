import json
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import runtime_manager as runtime


class RuntimeTests(unittest.TestCase):
    def test_gui_launcher_prefers_matching_windowless_interpreter(self):
        with tempfile.TemporaryDirectory() as folder:
            scripts = Path(folder) / 'Scripts'
            scripts.mkdir()
            python = scripts / 'python.exe'
            pythonw = scripts / 'pythonw.exe'
            python.touch()
            pythonw.touch()
            self.assertEqual(runtime.gui_interpreter(python), pythonw)
            pythonw.unlink()
            self.assertEqual(runtime.gui_interpreter(python), python)

    def test_migration_keeps_existing_extras_without_enabling_gesture_models(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / '.venv/Scripts/python.exe'
            source.parent.mkdir(parents=True)
            source.write_bytes(b'fixture')
            reply = Mock(stdout=json.dumps(['pypdf', 'soundcard', 'numpy', 'mediapipe']))
            with patch.object(runtime, 'ROOT', root), patch.object(runtime, 'CURRENT', root/'missing.json'), \
                    patch.object(runtime.subprocess, 'run', return_value=reply):
                self.assertEqual(runtime.installed_extras(), ['pypdf>=7,<8', 'SoundCard>=0.4,<1'])

    def test_project_checks_use_verified_managed_interpreter(self):
        from core.code_checks import _project_python
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            selected = root / '.jinx_runtime/envs/3.15.2/Scripts/python.exe'
            selected.parent.mkdir(parents=True)
            selected.write_bytes(b'fixture')
            (root / '.jinx_runtime/current.json').write_text(json.dumps({
                'python': 'envs/3.15.2/Scripts/python.exe'}))
            self.assertEqual(_project_python(root), str(selected))

    def test_latest_uses_stable_label_and_checksum_from_release_row(self):
        url = 'https://www.python.org/ftp/python/3.15.2/python-3.15.2-amd64.exe'
        sha = 'a' * 64
        pages = [b'Python 3.16.0a1 Latest Python 3 Release - Python 3.15.2',
                 ('<table><tr><td><a href="' + url + '">Windows</a></td><td>' + sha + '</td></tr></table>').encode()]
        with patch.object(runtime, 'fetch', side_effect=pages):
            self.assertEqual(runtime.latest(), ('3.15.2', url, sha))

    def test_missing_official_checksum_refuses_update(self):
        with patch.object(runtime, 'fetch', side_effect=[b'Latest Python 3 Release - Python 3.15.2', b'<table></table>']):
            with self.assertRaises(ValueError): runtime.latest()

    def test_target_honours_pinned_minor_and_skips_source_only_releases(self):
        """The pin decides the minor; a patch with no Windows installer is skipped.

        Security-only releases publish source tarballs and no .exe, so taking the
        newest patch of the pinned minor would fail on exactly the releases with
        nothing to install.
        """
        url = 'https://www.python.org/ftp/python/3.14.10/python-3.14.10-amd64.exe'
        sha = 'b' * 64
        index = (b'<a href="3.14.11/">3.14.11/</a> <a href="3.14.10/">3.14.10/</a> '
                 b'<a href="3.15.2/">3.15.2/</a>')
        pages = [index, b'<table></table>',
                 ('<table><tr><td><a href="' + url + '">Windows</a></td><td>' + sha + '</td></tr></table>').encode()]
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / '.python-version').write_text('3.14.10\n')
            with patch.object(runtime, 'ROOT', Path(folder)), \
                    patch.object(runtime, 'fetch', side_effect=pages):
                # 3.15.2 is newer, but the pin wins.
                self.assertEqual(runtime.target(), ('3.14.10', url, sha))

    def test_target_falls_back_to_latest_without_a_pin(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(runtime, 'ROOT', Path(folder)), \
                patch.object(runtime, 'latest', return_value=('9.9.9', 'url', 'sha')):
            self.assertEqual(runtime.target(), ('9.9.9', 'url', 'sha'))

    def test_installer_checksum_failure_never_executes_installer(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(runtime, 'STATE', Path(folder) / 'state'), \
                patch.dict(os.environ, {'LOCALAPPDATA': folder}), \
                patch.object(runtime, 'fetch', return_value=b'wrong installer'), \
                patch.object(runtime, 'run') as execute:
            with self.assertRaisesRegex(ValueError, 'checksum'):
                runtime.prepare('3.15.2', 'https://www.python.org/installer.exe', 'a' * 64, Mock())
            execute.assert_not_called()

    def test_failed_validation_preserves_previous_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / 'state'
            old = state / 'envs' / 'old' / 'python.exe'
            old.parent.mkdir(parents=True)
            old.write_bytes(b'fixture')
            current = state / 'current.json'
            contents = json.dumps({'python': 'envs/old/python.exe', 'version': '3.15.0'})
            current.write_text(contents)
            with patch.object(runtime, 'STATE', state), patch.object(runtime, 'CURRENT', current), \
                    patch.object(runtime, 'ROOT', Path(folder)), \
                    patch.object(runtime, 'latest', return_value=('3.15.2', 'url', 'sha')), \
                    patch.object(runtime, 'version_of', return_value='3.15.0'), \
                    patch.object(runtime, 'prepare', side_effect=RuntimeError('fixture failure')) as prepare, \
                    patch.object(runtime, 'sys', SimpleNamespace(platform='win32')), \
                    patch.dict('sys.modules', {'msvcrt': Mock()}), \
                    patch('sys.argv', ['runtime_manager.py']):
                self.assertEqual(runtime.main(), 1)
                prepare.assert_called_once()
            self.assertEqual(current.read_text(), contents)


if __name__ == '__main__': unittest.main()
