from pathlib import Path
import tempfile
import unittest

from core.multi_agent import AgentManager


PROFILE = """---
name: analyst
title: Analyst
description: Checks assumptions.
tools: notes
---
Answer with evidence and state uncertainty.
"""

SECOND = """---
name: critic
title: Critic
description: Looks for counterexamples.
tools: notes
---
Challenge unsupported conclusions.
"""


class MultiAgentTests(unittest.TestCase):
    def make_manager(self):
        folder = Path(tempfile.mkdtemp())
        (folder / "analyst.md").write_text(PROFILE, encoding="utf-8")
        (folder / "critic.md").write_text(SECOND, encoding="utf-8")
        return AgentManager(folder)

    def test_builtin_jinx_and_profiles_are_available(self):
        manager = self.make_manager()
        self.assertEqual(manager.current().name, "jinx")
        self.assertEqual(manager.names(), ["analyst", "critic", "jinx"])

    def test_switch_and_sessions_are_isolated(self):
        manager = self.make_manager()
        manager.switch("analyst")
        manager.add_turn("user", "private analyst turn")
        manager.switch("critic")
        self.assertEqual(manager.history(), [])
        manager.switch("analyst")
        self.assertEqual(manager.history(), ["user: private analyst turn"])

    def test_reset_is_explicit(self):
        manager = self.make_manager()
        manager.add_turn("user", "keep until reset")
        manager.reset()
        self.assertEqual(manager.history(), [])

    def test_oversized_and_malformed_profiles_are_ignored(self):
        folder = Path(tempfile.mkdtemp())
        (folder / "bad.md").write_text("not a profile", encoding="utf-8")
        (folder / "huge.md").write_text(
            "---\nname: huge\ntools: notes\n---\n" + "x" * 25_000,
            encoding="utf-8",
        )
        manager = AgentManager(folder)
        self.assertEqual(manager.names(), ["jinx"])

    def test_profile_content_is_not_executed(self):
        folder = Path(tempfile.mkdtemp())
        (folder / "safe.md").write_text(
            "---\nname: safe\ntools: notes\n---\n"
            "__import__('os').remove('important')",
            encoding="utf-8",
        )
        manager = AgentManager(folder)
        manager.switch("safe")
        self.assertIn("__import__", manager.active_context())
        # Loading is data-only; the test intentionally supplies no executable hook.
        self.assertIn("safe", manager.names())

    def test_debate_is_bounded_and_has_no_tools(self):
        manager = self.make_manager()
        calls = []

        def fake_ask(system, turns, declarations):
            calls.append((system, turns, declarations))
            return {"text": "short answer"}

        result = manager.debate("topic", turns=99, ask=fake_ask)
        self.assertEqual(len(calls), 8)
        self.assertTrue(result)
        self.assertTrue(all(item[2] is None for item in calls))


if __name__ == "__main__":
    unittest.main()
