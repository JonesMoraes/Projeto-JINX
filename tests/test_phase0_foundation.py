import unittest
import threading
from types import SimpleNamespace
from unittest.mock import patch

from adapters import os_adapter
from core.capability_manifest import build_manifest
from core import confirm
from core.events import EventBus


class EventBusTests(unittest.TestCase):
    def test_named_and_wildcard_subscribers_receive_immutable_envelope(self):
        bus = EventBus()
        received = []
        bus.subscribe("task.done", received.append)
        bus.subscribe("*", received.append)
        event = bus.publish("task.done", task_id="abc")
        self.assertEqual(event.payload["task_id"], "abc")
        self.assertEqual(len(received), 2)
        self.assertEqual(received[0], event)
        with self.assertRaises(TypeError):
            event.payload["task_id"] = "changed"

    def test_unsubscribe_is_idempotent(self):
        bus = EventBus()
        received = []
        remove = bus.subscribe("tick", received.append)
        remove()
        remove()
        bus.publish("tick")
        self.assertEqual(received, [])

    def test_subscriber_failure_does_not_block_other_subscribers(self):
        bus = EventBus()
        received = []
        bus.subscribe("tick", lambda _event: (_ for _ in ()).throw(RuntimeError("boom")))
        bus.subscribe("tick", received.append)
        bus.publish("tick")
        self.assertEqual(len(received), 1)


class CapabilityManifestTests(unittest.TestCase):
    def test_manifest_is_json_serializable_and_copies_registry_state(self):
        plugins = SimpleNamespace(list_for_ui=lambda: [
            {"name": "sample", "valid": True, "enabled": True, "file": "ignored.py"}])
        actions = SimpleNamespace(_all_records=[SimpleNamespace(
            name="open_app", valid=True, description="Launch", error="")])
        manifest = build_manifest(plugins=plugins, actions=actions,
                                  providers=[{"id": "llm-local", "kind": "llm",
                                              "label": "Local", "_available": True}],
                                  support=SimpleNamespace(os_name="TestOS", notes=[]))
        import json
        serialized = json.loads(json.dumps(manifest))
        self.assertEqual(serialized["platform"], "TestOS")
        self.assertEqual(serialized["plugins"][0]["name"], "sample")
        self.assertNotIn("file", serialized["plugins"][0])
        self.assertEqual(serialized["actions"][0]["name"], "open_app")
        self.assertEqual(serialized["providers"][0]["id"], "llm-local")


class OSAdapterTests(unittest.TestCase):
    def test_selects_supported_backends_without_claiming_host_switch(self):
        self.assertEqual(os_adapter.get_backend("Windows").os_name, "Windows")
        self.assertEqual(os_adapter.get_backend("macOS").os_name, "macOS")
        self.assertEqual(os_adapter.get_backend("Linux").os_name, "Linux")
        with self.assertRaises(ValueError):
            os_adapter.get_backend("Plan9")

    def test_foreign_backend_refuses_to_execute_on_this_host(self):
        backend = os_adapter.WindowsBackend()
        host = "Linux" if os_adapter.platform_name() != "Linux" else "Windows"
        with patch.object(os_adapter, "platform_name", return_value=host):
            result = backend.execute("launch_app", name="Calculator")
        self.assertIn("status=failed", result)

    def test_host_backend_delegates_to_verified_existing_action(self):
        backend = os_adapter.get_backend()
        with patch("actions.open_app.open_app", return_value="status=done action=open_app") as launch:
            result = backend.execute("launch_app", name="Calculator")
        self.assertIn("status=done", result)
        launch.assert_called_once_with({"app_name": "Calculator"})


class AutonomousActionTests(unittest.TestCase):
    def test_confirmation_request_runs_without_ui_approval(self):
        finished = threading.Event()
        result = confirm.request("test-autonomous", "Test action", "test detail",
                                 lambda: (finished.set(), "status=done action=test")[1])
        self.assertIn("status=started", result)
        self.assertTrue(finished.wait(2))
        self.assertEqual(confirm.pending_title(), "")


if __name__ == "__main__":
    unittest.main()
