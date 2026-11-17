import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.action_loader import discover_actions
from core.plugin_loader import discover_plugins
from memory import config_manager as config


class ExtensionPipelineIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.actions = self.root / "actions"
        self.plugins = self.root / "plugins"
        self.actions.mkdir()
        self.plugins.mkdir()
        self.addCleanup(self.temp.cleanup)

    def test_discovery_and_dispatch_cross_the_declared_contracts(self):
        (self.actions / "sample_action.py").write_text(
            "TOOL = {\n"
            "    'name': 'sample_action',\n"
            "    'description': 'Integration action',\n"
            "    'parameters': {'type': 'OBJECT', 'properties': {}},\n"
            "    'handler': lambda parameters, player=None: 'action:' + player,\n"
            "}\n",
            encoding="utf-8",
        )
        (self.plugins / "sample_plugin.py").write_text(
            "PLUGIN = {\n"
            "    'name': 'sample_plugin',\n"
            "    'description': 'Integration plugin',\n"
            "    'parameters': {'type': 'OBJECT', 'properties': {}},\n"
            "}\n"
            "def run(parameters, player=None, session_memory=None):\n"
            "    return 'plugin:' + player\n",
            encoding="utf-8",
        )

        actions = discover_actions(self.actions, logger=lambda _: None)
        plugins = discover_plugins(self.plugins, set(), logger=lambda _: None)

        self.assertEqual(actions.run("sample_action", {}, {"player": "ok"}), "action:ok")
        with patch("core.plugin_loader.get_plugin_enabled", return_value=True):
            self.assertEqual(plugins.run("sample_plugin", {}, player="ok"), "plugin:ok")
        self.assertEqual(actions.names(), {"sample_action"})
        self.assertEqual([row["name"] for row in plugins.list_for_ui()], ["sample_plugin"])

    def test_invalid_and_colliding_extensions_are_quarantined_without_blocking_valid_ones(self):
        (self.actions / "valid.py").write_text(
            "TOOL = {'name': 'valid', 'description': 'ok', 'handler': lambda parameters: 'ok'}\n",
            encoding="utf-8",
        )
        (self.actions / "collision.py").write_text(
            "TOOL = {'name': 'reserved', 'description': 'bad', 'handler': lambda parameters: 'bad'}\n",
            encoding="utf-8",
        )
        (self.actions / "broken.py").write_text("TOOL =", encoding="utf-8")

        registry = discover_actions(self.actions, {"reserved"}, logger=lambda _: None)

        self.assertEqual(registry.run("valid", {}, {}), "ok")
        self.assertFalse(registry.has("reserved"))
        records = {record.file: record for record in registry._all_records}
        self.assertFalse(records["collision.py"].valid)
        self.assertFalse(records["broken.py"].valid)

    def test_plugin_enablement_is_checked_at_dispatch_time(self):
        (self.plugins / "toggle.py").write_text(
            "PLUGIN = {'name': 'toggle', 'description': 'toggle', 'parameters': {'type': 'OBJECT'}}\n"
            "def run(parameters): return 'executed'\n",
            encoding="utf-8",
        )
        registry = discover_plugins(self.plugins, set(), logger=lambda _: None)
        with patch("core.plugin_loader.get_plugin_enabled", return_value=False):
            self.assertIn("disabled", registry.run("toggle", {}))
        with patch("core.plugin_loader.get_plugin_enabled", return_value=True):
            self.assertEqual(registry.run("toggle", {}), "executed")


class ConfigurationIntegrationTests(unittest.TestCase):
    def test_read_modify_write_preserves_existing_sections_across_features(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config_file = root / "api_keys.json"
            config_file.write_text(json.dumps({
                "gemini_api_key": "fixture-key",
                "providers": {"mode": "local"},
                "unrelated": {"keep": True},
            }), encoding="utf-8")
            with patch.object(config, "CONFIG_DIR", root), patch.object(config, "CONFIG_FILE", config_file):
                config.save_assistant_config("JINX Test", "User Test")
                config.save_plugin_config("sample", {"enabled": True, "mode": "safe"})
                config.save_plugin_enabled("sample", True)
                result = config.load_api_keys()

                self.assertEqual(result["gemini_api_key"], "fixture-key")
                self.assertEqual(result["providers"], {"mode": "local"})
                self.assertEqual(result["unrelated"], {"keep": True})
                self.assertEqual(result["assistant_name"], "JINX Test")
                self.assertEqual(result["user_name"], "User Test")
                self.assertEqual(result["plugin_config"]["sample"], {"enabled": True, "mode": "safe"})
                self.assertTrue(result["plugins_enabled"]["sample"])


if __name__ == "__main__":
    unittest.main()
