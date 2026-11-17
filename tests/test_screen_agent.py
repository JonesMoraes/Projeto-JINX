import unittest
from unittest.mock import patch, Mock

from plugins import screen_agent


class ScreenAgentTests(unittest.TestCase):
    def test_plugin_is_registered_with_opt_in_privacy_settings(self):
        self.assertEqual(screen_agent.PLUGIN["name"], "screen_agent")
        self.assertEqual(screen_agent.PLUGIN_SETTINGS["namespace"], "screen_agent")
        defaults = {field["key"]: field["default"]
                    for field in screen_agent.PLUGIN_SETTINGS["fields"]}
        self.assertFalse(defaults["allow_screen_context"])
        self.assertFalse(defaults["allow_screenshot"])

    def test_operate_does_not_inspect_screen_until_context_is_enabled(self):
        with patch.object(screen_agent, "get_plugin_config", return_value={}), \
             patch("core.screenview.look") as look:
            result = screen_agent._operate("Abra o navegador")
        self.assertIn("status=ask", result)
        look.assert_not_called()

    def test_status_reports_local_capabilities_without_ai(self):
        with patch("core.screenview.capabilities", return_value={"accessibility": True}), \
             patch("core.screenact.available", return_value=(True, "")), \
             patch.object(screen_agent, "get_plugin_config", return_value={}), \
             patch("core.gemini.text") as model:
            result = screen_agent._status()
        self.assertIn("status=done", result)
        self.assertIn("input_available=true", result)
        model.assert_not_called()

    def test_model_must_not_complete_without_visible_proof(self):
        view = Mock()
        view.app = "Calculator"
        view.pid = 1234
        view.contains_text.return_value = False
        with patch("core.screenview.look", return_value=view), \
             patch("core.screenview.is_own_pid", return_value=False), \
             patch("core.screenact.available", return_value=(True, "")), \
             patch("core.screenview.wait_stable"), \
             patch.object(screen_agent, "get_plugin_config", return_value={
                 "allow_screen_context": True}), \
             patch.object(screen_agent, "_request", return_value={
                 "action": "done", "proof": "Calculation complete"}):
            result = screen_agent._operate("Calculate 2 + 2")
        self.assertIn("status=unverified", result)


if __name__ == "__main__":
    unittest.main()
