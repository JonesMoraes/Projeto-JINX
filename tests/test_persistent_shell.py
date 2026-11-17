from __future__ import annotations

import platform
import unittest

from core.persistent_shell import PersistentShell


class PersistentShellTests(unittest.TestCase):
    def setUp(self):
        self.shell = PersistentShell()
        self.addCleanup(self.shell.close_all)

    def test_shell_keeps_environment_across_calls(self):
        session = self.shell.start()
        if platform.system() == "Windows":
            first = self.shell.execute(session, "$env:JINX_TEST_VALUE = 'kept'")
            second = self.shell.execute(session, "Write-Output $env:JINX_TEST_VALUE")
        else:
            first = self.shell.execute(session, "export JINX_TEST_VALUE=kept")
            second = self.shell.execute(session, "printf '%s\\n' \"$JINX_TEST_VALUE\"")
        self.assertIn("status=done", first)
        self.assertIn("status=done", second)
        self.assertIn("kept", second)

    def test_shell_sessions_are_isolated_and_parallel(self):
        one, two = self.shell.start(), self.shell.start()
        if platform.system() == "Windows":
            self.shell.execute(one, "$env:JINX_ISOLATED = 'one'")
            result = self.shell.execute(two, "Write-Output $env:JINX_ISOLATED")
        else:
            self.shell.execute(one, "export JINX_ISOLATED=one")
            result = self.shell.execute(two, "printf '%s' \"${JINX_ISOLATED-unset}\"")
        self.assertNotIn('output="one"', result)

    def test_unknown_session_and_invalid_command_fail(self):
        self.assertIn("status=failed", self.shell.execute("missing", "echo nope"))
        session = self.shell.start()
        self.assertIn("status=failed", self.shell.execute(session, " "))

    def test_close_removes_session(self):
        session = self.shell.start()
        self.assertTrue(self.shell.close(session))
        self.assertFalse(self.shell.close(session))
        self.assertEqual(self.shell.list(), [])


if __name__ == "__main__":
    unittest.main()
