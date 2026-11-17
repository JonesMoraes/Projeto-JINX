import ast
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core import boot_sentry, self_heal, skill_forge


class SelfHealTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        (self.root / "core").mkdir()
        (self.root / "core" / "safe.py").write_text("VALUE = 1\n", encoding="utf-8")
        self.state = self.root / "config" / "self_heal"
        self.patches = [
            patch.object(self_heal, "ROOT", self.root),
            patch.object(self_heal, "STATE", self.state),
            patch.object(boot_sentry, "ROOT", self.root),
            patch.object(boot_sentry, "STATE", self.state),
            patch.object(boot_sentry, "MARKER", self.state / "pending.json"),
            patch.dict(self_heal._pending, {}, clear=True),
        ]
        for p in self.patches: p.start()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(lambda: [p.stop() for p in reversed(self.patches)])

    def test_off_by_default_and_immune_paths(self):
        with patch.object(self_heal.config, "get_plugin_setting", return_value=False):
            self.assertFalse(self_heal.enabled())
        with self.assertRaises(ValueError): self_heal._target("main.py")
        with self.assertRaises(ValueError): self_heal._target("core/confirm.py")
        with self.assertRaises(ValueError): self_heal._target("../outside.py")

    def test_candidate_is_syntax_checked_and_confirmed_before_atomic_apply(self):
        with patch.object(self_heal, "enabled", return_value=True), \
                patch("core.gemini.text", return_value="VALUE = 2\n"):
            row = self_heal.propose("core/safe.py", "NameError in caller")
        player = Mock()
        player.show_review = Mock()
        confirm = patch.object(self_heal.confirm, "pending_title", return_value="")
        with patch.object(self_heal, "enabled", return_value=True), confirm, \
                patch.object(self_heal.confirm, "request", side_effect=lambda k,t,d,run: (run(), "queued")):
            result = self_heal.review(row["id"], player)
        self.assertIn("done", str(result))
        target = self.root / "core" / "safe.py"
        self.assertEqual(target.read_text(encoding="utf-8"), "VALUE = 2\n")
        self.assertTrue(any((self.state / "backups").glob("*.bak")))

    def test_boot_sentry_restores_interrupted_approved_transaction(self):
        backup = self.state / "backups" / "previous.bak"
        backup.parent.mkdir(parents=True)
        backup.write_text("VALUE = 1\n", encoding="utf-8")
        target = self.root / "core" / "safe.py"
        target.write_text("VALUE = broken(\n", encoding="utf-8")
        boot_sentry.MARKER.parent.mkdir(parents=True, exist_ok=True)
        boot_sentry.MARKER.write_text('{"target":"core/safe.py","backup":"backups/previous.bak"}', encoding="utf-8")
        self.assertTrue(boot_sentry.recover())
        self.assertEqual(target.read_text(encoding="utf-8"), "VALUE = 1\n")
        self.assertFalse(boot_sentry.MARKER.exists())

    def test_large_source_is_not_replaced_without_full_context(self):
        target = self.root / "core" / "safe.py"
        target.write_text("#" + ("x" * (self_heal.MAX_CANDIDATE + 1)), encoding="utf-8")
        with patch.object(self_heal, "enabled", return_value=True):
            with self.assertRaises(ValueError):
                self_heal.propose("core/safe.py", "repair this")

    def test_failed_validation_does_not_install_or_create_recovery_marker(self):
        with patch.object(self_heal, 'enabled', return_value=True), \
                patch('core.gemini.text', return_value='VALUE = missing_name\n'):
            row = self_heal.propose('core/safe.py', 'Fix value')
        with patch.object(self_heal, 'enabled', return_value=True), \
                patch.object(self_heal.confirm, 'pending_title', return_value=''), \
                patch.object(self_heal.confirm, 'request', side_effect=lambda k,t,d,run: run()):
            with self.assertRaisesRegex(ValueError, 'check failed'):
                self_heal.review(row['id'], Mock())
        self.assertEqual((self.root / 'core/safe.py').read_text(), 'VALUE = 1\n')
        self.assertFalse(boot_sentry.MARKER.exists())

    def test_changes_during_validation_are_preserved(self):
        target = self.root / 'core/safe.py'
        with patch.object(self_heal, 'enabled', return_value=True), \
                patch('core.gemini.text', return_value='VALUE = 2\n'):
            row = self_heal.propose('core/safe.py', 'Fix value')
        def concurrent_edit(*args):
            target.write_text('VALUE = 3\n')
            return 'import'
        with patch.object(self_heal, 'enabled', return_value=True), \
                patch.object(self_heal.confirm, 'pending_title', return_value=''), \
                patch.object(self_heal.confirm, 'request', side_effect=lambda k,t,d,run: run()), \
                patch('core._repair_check.validate', side_effect=concurrent_edit):
            result = self_heal.review(row['id'], Mock())
        self.assertIn('failed', result)
        self.assertEqual(target.read_text(), 'VALUE = 3\n')


class SkillForgeTests(unittest.TestCase):
    def test_skill_draft_is_bounded_inert_markdown(self):
        text = "# Name\n## Purpose\nHelp.\n## Workflow\nSteps.\n## Limits\nReview only."
        self.assertEqual(skill_forge.normalize_draft(text), text)
        for invalid in ("no title", text + "\n<script>alert(1)</script>", text[:30]):
            with self.assertRaises(ValueError): skill_forge.normalize_draft(invalid)

    def test_goal_is_validated_before_model_call(self):
        with self.assertRaises(ValueError): skill_forge.validate_goal("short")

class DevAgentGateTests(unittest.TestCase):
    def test_coding_task_is_dispatched_without_review_prompt(self):
        from actions import dev_agent
        params = {"mode": "build", "description": "Create a tiny app", "project_name": "demo"}
        player = Mock()
        with patch.object(dev_agent, "_start_build") as start, \
                patch("core.confirm.pending_title", return_value=""), \
                patch("core.confirm.request", return_value="status=started action=dev_agent") as request:
            result = dev_agent.dev_agent(params, player=player)
        self.assertEqual(result, "status=started action=dev_agent")
        start.assert_not_called()
        player.show_content.assert_called_once()
        self.assertEqual(request.call_args.args[0], "dev_agent")

    def test_dependencies_are_never_installed_from_generated_project(self):
        from actions import dev_agent
        with patch.object(dev_agent.subprocess, "run") as run:
            msg = dev_agent._install_dependencies(["some-large-package"], Path("."))
            self.assertIn("not installed automatically", msg)
            self.assertFalse(dev_agent._try_auto_install("No module named 'x'", Path(".")))
        run.assert_not_called()

    def test_generated_paths_and_run_commands_stay_inside_approved_folder(self):
        from actions import dev_agent
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve() / "approved"
            root.mkdir()
            self.assertEqual(dev_agent._project_file_path(root, "src/main.py"), root / "src" / "main.py")
            for path in ("../outside.py", "C:/outside.py", "src/../../outside.py"):
                with self.assertRaises(ValueError):
                    dev_agent._project_file_path(root, path)
            self.assertIsNone(dev_agent._safe_run_argv("python -c print(1)", root))
            self.assertIsNone(dev_agent._safe_run_argv("python ../../outside.py", root))
            with patch.object(dev_agent.subprocess, "run") as run:
                message = dev_agent._run_project("python -c print(1)", root)
            self.assertIn("was not a permitted", message)
            run.assert_not_called()

    def test_claude_cli_detection_does_not_run_or_install_cli(self):
        from actions import dev_agent
        with patch.object(dev_agent.shutil, "which", return_value=None) as which:
            self.assertFalse(dev_agent._claude_cli_available())
        which.assert_called_once_with("claude")


if __name__ == "__main__": unittest.main()
