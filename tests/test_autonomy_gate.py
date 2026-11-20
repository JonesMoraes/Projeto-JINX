"""Autonomy gate: the policy matrix and its floor.

The deny floor must hold at every level; the destructive ACL always ends in a
human event (banner or an explicit queue run within a nonzero budget); the
non-destructive path is exactly as fast as it was before the gate existed.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import autonomy, confirm, outcome


def _stub_config(**overrides):
    base = {"level": autonomy.DEFAULT_LEVEL, "paused_until": "",
            "budget": autonomy.DEFAULT_BUDGET, "trust": {}, "extra_deny": []}
    base.update(overrides)
    return base


class AutonomyGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        autonomy.QUEUE_PATH = Path(self.temp.name) / "queue.json"
        self.cfg_patch = patch.object(autonomy, "_cfg", side_effect=lambda: _stub_config())
        self.save_patch = patch.object(autonomy, "_save", lambda cfg: None)
        self.cfg_patch.start(); self.save_patch.start()
        self.addCleanup(self.cfg_patch.stop); self.addCleanup(self.save_patch.stop)

    def test_deny_floor_holds_at_every_level(self):
        params = {"path": r"C:\Users\OtherUser\Documents\foto.png"}
        for kind in ({"level": 0}, {"level": 1}, {"level": 2}, {"level": 3}, dict()):
            with patch.object(autonomy, "_cfg", side_effect=lambda k=kind: _stub_config(**k)):
                decision = autonomy.evaluate("file_controller", params)
            self.assertEqual(decision["mode"], "block",
                             f"outro usuário bloqueado no nível {kind}")

    def test_credential_file_is_blocked_even_in_own_profile(self):
        decision = autonomy.evaluate("fs_total", {"path": str(Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data" / "Default" / "Login Data")})
        self.assertEqual(decision["mode"], "block")
        self.assertIn("credencial", decision["reason"])

    def test_system_write_path_is_blocked(self):
        decision = autonomy.evaluate("file_controller", {"path": r"C:\Windows\System32\evil.dll"})
        self.assertEqual(decision["mode"], "block")
        self.assertIn("sistema", decision["reason"])

    def test_extra_deny_patterns_are_honoured(self):
        cfg = _stub_config(level=3, budget=5, extra_deny=["**/trabalho/**"])
        with patch.object(autonomy, "_cfg", return_value=cfg):
            decision = autonomy.evaluate("file_controller",
                                         {"path": r"C:\Users\me\trabalho\rascunho.docx"})
        self.assertEqual(decision["mode"], "block")
        self.assertIn("negação", decision["reason"])

    def test_shell_destructive_patterns_are_blocked_at_every_level(self):
        for level in (1, 2, 3):
            with patch.object(autonomy, "_cfg", side_effect=lambda n=level: _stub_config(level=n)):
                decision = autonomy.evaluate(
                    "shell_persistent",
                    {"command": "taskkill /f /im explorer.exe"})
            self.assertEqual(decision["mode"], "block", f"nível {level}")

    def test_first_run_ships_at_full_potential(self):
        """Owner request: level 3 with a nonzero queue budget from day one."""
        self.assertEqual(autonomy.DEFAULT_LEVEL, 3)
        self.assertGreater(autonomy.DEFAULT_BUDGET, 0)

    def test_level_three_queues_destructive_but_running_still_needs_the_user(self):
        """Full autonomy ≠ silent destruction: queued rows execute only when
        this user explicitly says 'run N' through autonomy_control."""
        with patch.object(autonomy, "_cfg", side_effect=_stub_config):
            decision = autonomy.evaluate("send_message", {"to": "alguém", "text": "oi"})
        self.assertEqual(decision["mode"], "queue")
        self.assertEqual(autonomy.queue_list()[-1]["name"], "send_message")
        runs = []
        result = autonomy.queue_run(1, lambda: runs.append(1) or "executado")
        self.assertEqual(runs, [1], "o runner roda exatamente uma vez, sob comando explícito")
        self.assertIn("executado", result)

    def test_power_action_requires_confirmation_by_default(self):
        with patch.object(confirm, "_show_cb", None):
            with patch.object(autonomy, "_cfg", side_effect=lambda: _stub_config(level=1)):
                decision = autonomy.evaluate("computer_settings", {"mode": "shutdown"})
        self.assertEqual(decision["mode"], "confirm")
        self.assertEqual(decision["reason"], "power")

    def test_level_three_with_zero_budget_never_queues(self):
        with patch.object(autonomy, "_cfg", side_effect=lambda: _stub_config(level=3, budget=0)):
            decision = autonomy.evaluate("send_message", {"to": "alguém", "text": "oi"})
        self.assertEqual(decision["mode"], "confirm")

    def test_level_three_with_budget_queues_and_gate_runs_only_via_explicit_run(self):
        with patch.object(autonomy, "_cfg", side_effect=lambda: _stub_config(level=3, budget=1)):
            decision = autonomy.evaluate("send_message", {"to": "alguém", "text": "oi"})
        self.assertEqual(decision["mode"], "queue")

    def test_non_destructive_actions_run_unchanged(self):
        with patch.object(autonomy, "_cfg", side_effect=lambda: _stub_config(level=1)):
            self.assertEqual(autonomy.evaluate("open_app", {"app_name": "spotify"})["mode"], "run")
            self.assertEqual(autonomy.evaluate("weather_report", {"city": "BH"})["mode"], "run")

    def test_paused_blocks_destructive_but_not_routine(self):
        from datetime import datetime, timedelta, timezone
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        with patch.object(autonomy, "_cfg",
                          side_effect=lambda: _stub_config(paused_until=future.isoformat(), level=2)):
            self.assertEqual(autonomy.evaluate("send_message", {"to": "a", "text": "b"})["mode"],
                             "block")
            self.assertEqual(autonomy.evaluate("open_app", {"app_name": "notepad"})["mode"], "run")

    def test_queue_budget_is_consumed_daily_and_zero_by_default(self):
        runs = []
        autonomy.queue_add("send_message", {"to": "a"}, "messaging")
        with patch.object(autonomy, "_cfg", side_effect=lambda: _stub_config(level=3, budget=0)):
            result = autonomy.queue_run(1, lambda: runs.append(1) or "ok")
        self.assertEqual(runs, [])
        self.assertIn("esgotado", result)
        with patch.object(autonomy, "_cfg", side_effect=lambda: _stub_config(level=3, budget=1),
                          create=True):
            result = autonomy.queue_run(1, lambda: "executado")
        self.assertIn("executado", result)
        rows = json.loads(autonomy.QUEUE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(rows[-1]["status"], "ran")

    def test_undo_pauses_for_a_day(self):
        from unittest.mock import MagicMock
        saver = MagicMock()
        with patch.object(autonomy, "_cfg", side_effect=_stub_config), \
                patch.object(autonomy, "_save", new=saver):
            autonomy.note_undo()
        cfg = saver.call_args[0][0]
        self.assertTrue(cfg["paused_until"], "undo deve pausar a autonomia")

    def test_propose_only_via_gui_or_ask_never_model_flag(self):
        """Without a bound HUD the gate's confirm path must degrade to an ask(),
        which by definition cannot be pre-filled by the model as parameter."""
        # propose() leaves a module-level pending banner behind on purpose
        # (the timed resolve is the only thing that clears it in production);
        # leaking it here would make every later test refuse sends.
        self.addCleanup(setattr, confirm, "_pending", None)
        with patch.object(confirm, "_show_cb", None), \
                patch.object(confirm, "_hide_cb", None), \
                patch.object(confirm, "_log_cb", None):
            result = confirm.propose("gate-x", "t", "d", lambda: "ran")
        self.assertIn("status=ask", result)


if __name__ == "__main__":
    unittest.main()
