import os
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from actions import process_manager as manager
from core import confirm


class ProcessTest(unittest.TestCase):
    def setUp(self):
        manager._attempts.clear()
        self.addCleanup(manager._attempts.clear)
        self.target = manager.Target(50000, 10., "editor.exe", "C:\\Apps\\editor.exe")
        self.process = Mock(pid=50000)
        self.process.create_time.return_value = 10.
        self.process.exe.return_value = self.target.exe
        self.process.name.return_value = "editor.exe"
        for target, value in (("own_pids", set()), ("own_exes", set())):
            p = patch.object(manager.appidentity, target, return_value=value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(manager.psutil, "Process", return_value=self.process)
        p.start()
        self.addCleanup(p.stop)

    def test_cpu_sampling_normalized_to_total_capacity(self):
        first = {1: {"pid": 1, "name": "app", "created": 1, "rss": 1048576, "seconds": 10}}
        second = {1: {**first[1], "seconds": 11}}
        with patch.object(manager, "_snapshots", side_effect=[first, second]), \
             patch.object(manager.time, "monotonic", side_effect=[0., 1.]), patch.object(manager.time, "sleep"), \
             patch.object(manager.psutil, "cpu_count", return_value=4):
            rows = manager.inspect_processes("cpu", 10)
        self.assertEqual(rows[0]["cpu_total_percent"], 25.)
        self.assertEqual(rows[0]["ram_mib"], 1.)

    def test_reused_pid_not_in_cpu_sample(self):
        row = {"pid": 1, "name": "app", "created": 1, "rss": 1, "seconds": 10}
        with patch.object(manager, "_snapshots", side_effect=[{1: row}, {1: {**row, "created": 2}}]), patch.object(manager.time, "sleep"):
            self.assertEqual(manager.inspect_processes("cpu"), [])

    def test_ram_ranking_and_name_filter(self):
        rows = {1: {"pid": 1, "name": "a.exe", "created": 1, "rss": 100, "seconds": 0},
                2: {"pid": 2, "name": "b.exe", "created": 1, "rss": 200, "seconds": 0}}
        with patch.object(manager, "_snapshots", return_value=rows):
            self.assertEqual(manager.inspect_processes()[0]["pid"], 2)
            self.assertEqual(manager.inspect_processes(name="A")[0]["pid"], 1)

    def test_close_dispatches_autonomously(self):
        with patch.object(manager.confirm, "request", return_value="status=started") as request:
            result = manager.process_manager({"action": "close", "pid": 50000, "confirmed": True})
            self.assertEqual(result, "status=started")
            request.assert_called_once()
            self.process.kill.assert_not_called()
            self.process.terminate.assert_not_called()

    def test_guard_own_process_both_before_and_after_confirmation(self):
        with patch.object(manager.appidentity, "own_pids", return_value={50000}), patch.object(manager.confirm, "request") as gate:
            self.assertTrue(manager.process_manager({"action": "close", "pid": 50000}).startswith("status=failed"))
            gate.assert_not_called()
        manager._attempts.add((50000, 10.))
        with patch.object(manager.appidentity, "own_pids", return_value={50000}):
            self.assertIn("status=failed", manager._perform((self.target,), True))
        self.process.kill.assert_not_called()

    def test_same_executable_protected(self):
        with patch.object(manager.appidentity, "own_exes", return_value={os.path.normcase(self.target.exe)}):
            with self.assertRaises(ValueError):
                manager._guard(self.target)

    def test_pid_reuse_after_confirmation_is_refused(self):
        self.process.create_time.return_value = 20.
        manager._attempts.add((50000, 10.))
        result = manager._perform((self.target,), True)
        self.assertIn("status=failed", result)
        self.process.kill.assert_not_called()

    def test_windows_close_without_window_never_terminates(self):
        with patch.object(manager.platform, "system", return_value="Windows"), \
             patch.object(manager.appidentity, "_post_close_windows", return_value=0):
            self.assertTrue(manager._close(self.target).startswith("status=unverified"))
        self.process.terminate.assert_not_called()
        self.process.kill.assert_not_called()
        self.assertIn((50000, 10.), manager._attempts)

    def test_graceful_close_and_exit_readback(self):
        with patch.object(manager.platform, "system", return_value="Windows"), \
             patch.object(manager.appidentity, "_post_close_windows", return_value=1), patch.object(manager, "_wait", return_value=True):
            self.assertTrue(manager._close(self.target).startswith("status=done"))
        self.process.kill.assert_not_called()

    def test_force_without_graceful_attempt_is_refused(self):
        with patch.object(manager.confirm, "request") as gate:
            result = manager.process_manager({"action": "force", "pid": 50000})
            self.assertTrue(result.startswith("status=failed"))
            gate.assert_not_called()
        self.process.kill.assert_not_called()

    def test_force_dispatches_after_graceful_attempt(self):
        manager._attempts.add((50000, 10.))
        with patch.object(manager.confirm, "request", return_value="pending") as gate:
            self.assertEqual(manager.process_manager({"action": "force", "pid": 50000}), "pending")
            callback = gate.call_args.args[3]
            self.process.kill.assert_not_called()
            with patch.object(manager, "_wait", return_value=True):
                self.assertTrue(callback().startswith("status=done"))
            self.process.kill.assert_called_once()

    def test_force_without_exit_verification_is_unverified(self):
        manager._attempts.add((50000, 10.))
        with patch.object(manager, "_wait", return_value=False):
            self.assertTrue(manager._force(self.target).startswith("status=unverified"))

    def test_system_and_invalid_pids_refused(self):
        for pid in (True, -1, 0):
            self.assertTrue(manager.process_manager({"action": "close", "pid": pid}).startswith("status=failed"))
        with self.assertRaises(ValueError):
            manager._guard(manager.Target(4, 0, "System", "system"))

    def test_ambiguous_or_title_only_name_refused(self):
        with patch.object(manager.appidentity, "running", return_value=[SimpleNamespace(pid=5, name="app.exe", score=20)]):
            with self.assertRaises(ValueError):
                manager._targets(name="document title")

    def test_close_runs_asynchronously_without_hud_confirmation(self):
        finished = threading.Event()
        with patch.object(manager, "_perform", side_effect=lambda *_args, **_kwargs:
                          (finished.set(), "status=done action=process_close")[1]) as perform:
            result = manager.process_manager({"action": "close", "pid": 50000})
            self.assertIn("status=started", result)
            self.assertTrue(finished.wait(2))
            perform.assert_called_once()
        self.assertEqual(confirm.pending_title(), "")


if __name__ == "__main__":
    unittest.main()
