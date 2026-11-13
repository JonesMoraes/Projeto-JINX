"""No network or real credentials: exercise fallback in the actual ladder."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from core import gemini, gemini_accounts as accounts


class AccountsTest(unittest.TestCase):
    def setUp(self):
        accounts._rest.clear()
        gemini._cooldown.clear()
        gemini._gone.clear()
        self.cfg = patch.object(accounts, "load_api_keys", return_value={
            "gemini_api_key": "fake-A", "plugin_config": {"gemini": {
                "secondary_key": "fake-B", "tertiary_key": "fake-C"}}})
        self.cfg.start()
        self.addCleanup(self.cfg.stop)
        self.addCleanup(accounts._rest.clear)

    def test_real_ladder_retries_same_model_on_next_account(self):
        seen = []
        def make_client(timeout_ms, key):
            def generate(**kwargs):
                seen.append((key, kwargs["model"]))
                if key == "fake-A":
                    raise RuntimeError("429 RESOURCE_EXHAUSTED")
                return SimpleNamespace(text="ok")
            return SimpleNamespace(models=SimpleNamespace(generate_content=generate))
        with patch.dict(gemini._LADDERS, {gemini.FAST: ("test-model",)}), \
             patch.object(gemini, "_provider_rungs", return_value=()), \
             patch.object(gemini, "client", side_effect=make_client):
            self.assertEqual(gemini.call("hello").text, "ok")
            self.assertEqual(gemini.call("again").text, "ok")
        self.assertEqual(seen, [("fake-A", "test-model"), ("fake-B", "test-model"),
                                ("fake-B", "test-model")])
        self.assertNotIn("test-model", gemini._cooldown)

    def test_rejected_and_expired_rest(self):
        with patch.object(accounts.time, "monotonic", return_value=10):
            accounts.rest("fake-A", True)
            self.assertEqual(accounts.select(), "fake-B")
        with patch.object(accounts.time, "monotonic", return_value=10 + accounts.REJECTED_REST):
            self.assertEqual(accounts.select(), "fake-A")

    def test_explicit_credentials_never_fall_back(self):
        seen = []
        def fail(key):
            seen.append(key)
            raise RuntimeError("429")
        with self.assertRaises(RuntimeError):
            accounts.attempt(fail, "caller-key")
        self.assertEqual(seen, ["caller-key"])
        self.assertEqual(accounts.select(), "fake-A")

    def test_all_resting_and_no_secret_in_status(self):
        for key in accounts.configured():
            accounts.rest(key)
        self.assertEqual(accounts.select(), "")
        with self.assertRaises(RuntimeError):
            accounts.attempt(lambda key: self.fail("must not call network"))
        self.assertNotIn("fake-", accounts.status())

    def test_config_edits_apply_without_restart(self):
        self.assertEqual(accounts.select(), "fake-A")
        with patch.object(accounts, "load_api_keys", return_value={"gemini_api_key": "new"}):
            self.assertEqual(accounts.select(), "new")

    def test_existing_action_passing_primary_still_rotates(self):
        def invoke(key):
            if key == "fake-A":
                raise RuntimeError("429 RESOURCE_EXHAUSTED")
            return key
        self.assertEqual(accounts.attempt(invoke, "fake-A"), "fake-B")

    def test_non_quota_error_does_not_rotate(self):
        with self.assertRaisesRegex(RuntimeError, "503"):
            accounts.attempt(lambda key: (_ for _ in ()).throw(RuntimeError("503")))
        self.assertEqual(accounts.select(), "fake-A")

    def test_live_rung_rotates_without_cooling_model(self):
        seen = []
        def live(contents, config, timeout, key):
            seen.append(key)
            if key == "fake-A":
                raise RuntimeError("API key not valid")
            return SimpleNamespace(text="live-ok")
        with patch.dict(gemini._LADDERS, {gemini.FAST: (gemini.LIVE,)}), \
             patch.object(gemini, "_provider_rungs", return_value=()), \
             patch.object(gemini, "_live_call", side_effect=live):
            self.assertEqual(gemini.call("hi").text, "live-ok")
        self.assertEqual(seen, ["fake-A", "fake-B"])
        self.assertFalse(gemini._cooldown)

    def test_provider_fallback_when_all_accounts_rest(self):
        for key in accounts.configured():
            accounts.rest(key)
        rung = gemini.PROVIDER_PREFIX + "fake-provider"
        with patch.dict(gemini._LADDERS, {gemini.FAST: ("test-model",)}), \
             patch.object(gemini, "_provider_rungs", return_value=(rung,)), \
             patch.object(gemini, "_provider_first", return_value=False), \
             patch.object(gemini, "_provider_call", return_value="fallback"):
            self.assertEqual(gemini.call("hi"), "fallback")


if __name__ == "__main__":
    unittest.main()
