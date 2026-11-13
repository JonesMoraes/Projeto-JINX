import asyncio
import ast
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from core import battery, undo
from memory import config_manager as config
from plugins import battery_health


class BatteryTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        for key, value in (("CONFIG_DIR", Path(temp.name)), ("CONFIG_FILE", Path(temp.name) / "api_keys.json")):
            p = patch.object(config, key, value)
            p.start()
            self.addCleanup(p.stop)
        undo.clear()
        self.addCleanup(undo.clear)

    def reading(self, percent=15, plugged=False, seconds=600):
        return SimpleNamespace(percent=percent, power_plugged=plugged, secsleft=seconds)

    def test_no_battery(self):
        with patch.object(battery.psutil, "sensors_battery", return_value=None), patch.object(battery, "health") as health:
            self.assertIn("status=unverified", battery_health.run({"action": "status"}))
            health.assert_not_called()

    def test_power_connected_does_not_claim_charging(self):
        with patch.object(battery.psutil, "sensors_battery", return_value=self.reading(80, True)):
            result = battery.snapshot()
        self.assertEqual(result["state"], "power_connected_charging_unknown")
        self.assertIsNone(result["remaining_minutes_estimate"])

    def test_unknown_remaining_and_power(self):
        for plugged in (False, None):
            with patch.object(battery.psutil, "sensors_battery", return_value=self.reading(50, plugged, -1)):
                self.assertIsNone(battery.snapshot()["remaining_minutes_estimate"])

    def test_discharge_time_and_invalid_percent(self):
        with patch.object(battery.psutil, "sensors_battery", return_value=self.reading()):
            self.assertEqual(battery.snapshot()["remaining_minutes_estimate"], 10)
        for percent in (float("nan"), -1, 101):
            with patch.object(battery.psutil, "sensors_battery", return_value=self.reading(percent)):
                with self.assertRaises(ValueError):
                    battery.snapshot()

    def test_windows_health_ratio_and_hidden_bounded_query(self):
        data = [{"design": 50000, "full": 40000}, {"design": 30000, "full": 31500}]
        with patch.object(battery.platform, "system", return_value="Windows"), \
             patch.object(battery.subprocess, "run", return_value=SimpleNamespace(stdout=json.dumps(data))) as run:
            result = battery.health()
        self.assertEqual(result["packs"][0]["wear_percent_estimate"], 20)
        self.assertEqual(result["packs"][1]["capacity_percent_estimate"], 105)
        self.assertEqual(result["packs"][1]["wear_percent_estimate"], 0)
        self.assertEqual(run.call_args.kwargs["timeout"], 4)
        self.assertNotIn("shell", run.call_args.kwargs)

    def test_health_invalid_zero_sentinel_and_missing(self):
        for data in ([], {"design": 0, "full": 100}, {"design": 100, "full": 4294967295}, {"wrong": 100}):
            with patch.object(battery.platform, "system", return_value="Windows"), \
                 patch.object(battery.subprocess, "run", return_value=SimpleNamespace(stdout=json.dumps(data))):
                self.assertEqual(battery.health()["status"], "unverified")

    def test_health_timeout_and_non_windows(self):
        with patch.object(battery.platform, "system", return_value="Windows"), \
             patch.object(battery.subprocess, "run", side_effect=TimeoutError):
            self.assertEqual(battery.health()["status"], "unverified")
        with patch.object(battery.platform, "system", return_value="Linux"), patch.object(battery.subprocess, "run") as run:
            self.assertEqual(battery.health()["status"], "unverified")
            run.assert_not_called()

    def test_configure_persists_undo_restores_effective_defaults(self):
        self.assertFalse(battery.settings()["enabled"])
        self.assertIn("status=done", battery_health.run({"action": "alerts", "low": 25, "high": 85}))
        self.assertEqual(battery.settings(), {"enabled": True, "low": 25, "high": 85})
        undo.undo_last()
        self.assertEqual(battery.settings(), {"enabled": False, "low": 20, "high": 80})

    def test_invalid_thresholds_leave_settings_unchanged(self):
        for p in ({"low": 80, "high": 20}, {"low": 0}, {"high": 101}, {"low": True}, {"low": 20.5}):
            self.assertIn("status=failed", battery_health.run({"action": "alerts", **p}))
            self.assertFalse(battery.settings()["enabled"])

    def test_undo_does_not_overwrite_new_settings(self):
        battery.configure({"enabled": True})
        config.save_plugin_config("battery", {"low": "30"})
        self.assertIn("status=failed", undo.undo_last())
        self.assertEqual(battery.settings()["low"], 30)

    def test_disable_and_failed_write(self):
        battery.configure({"enabled": True})
        self.assertIn("status=done", battery_health.run({"action": "disable"}))
        self.assertFalse(battery.settings()["enabled"])
        with patch.object(battery, "save_plugin_config"):
            self.assertIn("status=failed", battery_health.run({"action": "alerts"}))

    def test_alert_latch_hysteresis_and_cooldown(self):
        alerts = battery.BatteryAlerts()
        cfg = {"enabled": True, "low": 20, "high": 80}
        with patch.object(battery, "get_plugin_enabled", return_value=True):
            self.assertEqual(alerts.pending({"percent": 20, "power_connected": False}, cfg, now=0), "low")
            alerts.delivered("low", now=0)
            self.assertIsNone(alerts.pending({"percent": 19, "power_connected": False}, cfg, now=600))
            alerts.pending({"percent": 24, "power_connected": False}, cfg, now=601)
            self.assertEqual(alerts.pending({"percent": 19, "power_connected": False}, cfg, now=602), "low")
            alerts.delivered("low", now=602)
            self.assertIsNone(alerts.pending({"percent": 90, "power_connected": True}, cfg, now=603))
            self.assertEqual(alerts.pending({"percent": 90, "power_connected": True}, cfg, now=903), "high")

    def host(self):
        return SimpleNamespace(session=SimpleNamespace(send_client_content=AsyncMock()), _awake=True,
            ui=SimpleNamespace(muted=False), _is_speaking=False, _last_user_speech=-100000,
            _routines=SimpleNamespace(in_quiet=Mock(return_value=False)))

    def test_quiet_busy_muted_sleep_and_recent_speech_defer(self):
        battery.configure({"enabled": True})
        host = self.host()
        alerts = battery.BatteryAlerts()
        with patch.object(battery, "snapshot", return_value={"percent": 10, "power_connected": False}):
            host._routines.in_quiet.return_value = True
            asyncio.run(battery.poll(host, alerts))
            host._routines.in_quiet.return_value = False
            for field in ("_is_speaking", "_awake"):
                before = getattr(host, field)
                setattr(host, field, not before)
                asyncio.run(battery.poll(host, alerts))
                setattr(host, field, before)
            host.ui.muted = True
            asyncio.run(battery.poll(host, alerts))
            host.ui.muted = False
            with patch.object(battery.time, "monotonic", return_value=0):
                host._last_user_speech = 0
                asyncio.run(battery.poll(host, alerts))
            host._last_user_speech = -100000
            host.session.send_client_content.assert_not_awaited()
            self.assertEqual(alerts.sent, set())
            asyncio.run(battery.poll(host, alerts))
            asyncio.run(battery.poll(host, alerts))
            host.session.send_client_content.assert_awaited_once()

    def test_failed_send_does_not_consume_alert(self):
        battery.configure({"enabled": True})
        host, alerts = self.host(), battery.BatteryAlerts()
        host.session.send_client_content.side_effect = RuntimeError("offline")
        with patch.object(battery, "snapshot", return_value={"percent": 10, "power_connected": False}):
            with self.assertRaises(RuntimeError):
                asyncio.run(battery.poll(host, alerts))
        self.assertFalse(alerts.sent)

    def test_disabled_plugin_and_default_never_sample_or_speak(self):
        host = self.host()
        with patch.object(battery, "snapshot") as read:
            asyncio.run(battery.poll(host, battery.BatteryAlerts()))
            battery.configure({"enabled": True})
            with patch.object(battery, "get_plugin_enabled", return_value=False):
                asyncio.run(battery.poll(host, battery.BatteryAlerts()))
            read.assert_not_called()
        host.session.send_client_content.assert_not_awaited()

    def test_monitor_registered_and_cancellable(self):
        # Extract the host coroutine without importing main.py (which boots audio).
        tree = ast.parse(Path("main.py").read_text(encoding="utf-8"))
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "_run_battery_monitor")
        namespace = {"asyncio": asyncio}
        exec(compile(ast.Module(body=[method], type_ignores=[]), "main.py", "exec"), namespace)
        async def check():
            host = self.host()
            with patch.object(battery, "poll", new=AsyncMock()) as tick:
                calls = 0
                async def sleep(_):
                    nonlocal calls
                    calls += 1
                    if calls > 1:
                        raise asyncio.CancelledError
                with patch.object(asyncio, "sleep", side_effect=sleep):
                    with self.assertRaises(asyncio.CancelledError):
                        await namespace["_run_battery_monitor"](host)
                tick.assert_awaited_once()
        asyncio.run(check())
        self.assertIn("tg.create_task(self._run_battery_monitor())", ast.unparse(tree))


if __name__ == "__main__":
    unittest.main()
