import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import _repair_check


class RepairValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / 'core').mkdir()
        (self.root / 'core' / '__init__.py').write_text('')
        self.target = self.root / 'core' / 'sample.py'
        self.target.write_text('VALUE = 1\n')
        self.log = self.root / 'config' / 'self_heal' / 'repair-validation.log'

    def validate(self, candidate):
        return _repair_check.validate(self.root, 'core/sample.py', candidate, self.log)

    def test_valid_import_does_not_change_original_or_copy_settings(self):
        settings = self.root / 'config' / 'api_keys.json'
        settings.parent.mkdir()
        settings.write_text('{"test_secret": "fixture-only"}')
        candidate = ('from pathlib import Path\n'
                     'assert not Path("config/api_keys.json").exists()\nVALUE = 2\n')
        self.assertIn('import', self.validate(candidate))
        self.assertEqual(self.target.read_text(), 'VALUE = 1\n')
        self.assertEqual(settings.read_text(), '{"test_secret": "fixture-only"}')

    def test_runtime_error_with_valid_syntax_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'check failed'):
            self.validate('VALUE = missing_name\n')
        self.assertEqual(self.target.read_text(), 'VALUE = 1\n')
        self.assertIn('NameError', self.log.read_text())

    def test_dedicated_tests_reject_functional_regression(self):
        tests = self.root / 'tests'
        tests.mkdir()
        (tests / 'test_sample.py').write_text(
            'import unittest\nfrom core.sample import VALUE\n'
            'class SampleTest(unittest.TestCase):\n'
            '    def test_value(self): self.assertEqual(VALUE, 1)\n')
        with self.assertRaisesRegex(ValueError, 'check failed'):
            self.validate('VALUE = 2\n')
        self.assertEqual(self.target.read_text(), 'VALUE = 1\n')
        self.assertIn('AssertionError', self.log.read_text())

    def test_timeout_preserves_original_and_keeps_diagnostic(self):
        timeout = subprocess.TimeoutExpired('python', 20, output=b'partial output')
        with patch.object(_repair_check.subprocess, 'run', side_effect=timeout):
            with self.assertRaisesRegex(ValueError, 'timed out'):
                self.validate('VALUE = 2\n')
        self.assertEqual(self.target.read_text(), 'VALUE = 1\n')
        self.assertIn('partial output', self.log.read_text())


if __name__ == '__main__':
    unittest.main()
