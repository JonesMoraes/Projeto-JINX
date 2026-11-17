import unittest

from actions.repl_polyglot import ReplManager


class ReplPolyglotTests(unittest.TestCase):
    def setUp(self):
        self.repl = ReplManager()
        self.addCleanup(lambda: [self.repl.close(row["session_id"], force=True)
                                 for row in self.repl.list()])

    def test_python_repl_persists_names_and_returns_expression(self):
        session = self.repl.start("python")
        first = self.repl.evaluate(session, "counter = 40\ncounter + 2")
        second = self.repl.evaluate(session, "counter += 1\ncounter")
        self.assertIn("status=done", first)
        self.assertIn("42", first)
        self.assertIn("41", second)

    def test_eval_timeout_closes_worker(self):
        session = self.repl.start("python")
        result = self.repl.evaluate(session, "while True: pass", timeout=1)
        self.assertIn("status=failed", result)
        self.assertEqual(self.repl.list(), [])

    def test_node_repl_if_installed(self):
        import shutil
        if not shutil.which("node"):
            self.skipTest("Node.js is optional and is not installed")
        session = self.repl.start("javascript")
        self.assertIn("3", self.repl.evaluate(session, "let answer = 1 + 2; answer"))
        self.assertIn("3", self.repl.evaluate(session, "answer"))


if __name__ == "__main__":
    unittest.main()
