import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from core import watchers as w, undo
from memory import config_manager as config


class WatchersTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        for key, val in (("CONFIG_DIR", Path(temp.name)), ("CONFIG_FILE", Path(temp.name) / "api_keys.json")):
            p = patch.object(config, key, val); p.start(); self.addCleanup(p.stop)
        undo.clear(); self.addCleanup(undo.clear)
        self.row = {"id": "a", "kind": "ram", "interval": 60, "threshold": 90, "direction": "above"}

    def test_crud_undo_and_invalid_interval(self):
        rows = w.change("add", {"kind": "ram", "threshold": 90})
        self.assertEqual(len(rows), 1)
        self.assertNotIn("enabled", config.get_plugin_config("system_watchers"))
        undo.undo_last(); self.assertEqual(w.entries(), [])
        with self.assertRaises(ValueError): w.change("add", {"kind": "ram", "interval": 1})

    def test_private_and_credentials_urls_refused(self):
        for url in ("https://127.0.0.1/test", "https://user:pass@example.com", "file:///etc/passwd"):
            with self.assertRaises(ValueError): w.change("add", {"kind": "website", "url": url})

    def test_quiet_deferred_interval_and_episode_dedup(self):
        m = w.Monitor()
        with patch.object(w, "sample", return_value=95) as sample:
            self.assertEqual(m.check([self.row], False, now=0), [])
            self.assertEqual(len(m.check([self.row], True, now=1)), 1)
            sample.assert_called_once()
            m.delivered("a")
            self.assertEqual(m.check([self.row], True, now=60), [])
        with patch.object(w, "sample", return_value=80): m.check([self.row], now=120)
        with patch.object(w, "sample", return_value=95): self.assertEqual(len(m.check([self.row], now=180)), 1)

    def test_quote_error_is_not_threshold(self):
        with patch.object(w, "sample", side_effect=RuntimeError("429")):
            self.assertEqual(w.Monitor().check([self.row], now=0), [])

    def test_website_recovers_and_second_outage_alerts(self):
        row = {**self.row, "kind": "website"}
        m = w.Monitor()
        with patch.object(w, "sample", side_effect=[False, True, False]):
            for now in (0, 60, 120):
                self.assertEqual(len(m.check([row], now=now)), 1)
                m.delivered("a")

    def test_head_does_not_follow_redirect(self):
        response = Mock(status_code=302)
        response.__enter__ = Mock(return_value=response); response.__exit__ = Mock(return_value=None)
        with patch("core.tasks.web.check_url", return_value="https://example.com"), patch.object(w.requests, "head", return_value=response) as head:
            self.assertTrue(w.sample({"kind": "website", "url": "https://example.com"}))
            self.assertFalse(head.call_args.kwargs["allow_redirects"])

    def test_crypto_invalid_and_endpoint(self):
        with self.assertRaises(ValueError): w.change("add", {"kind": "crypto", "coin": "../../x"})
        response = Mock(); response.__enter__ = Mock(return_value=response); response.__exit__ = Mock(return_value=None)
        response.json.return_value = {"bitcoin": {"brl": 123}}
        with patch.object(w.requests, "get", return_value=response) as get:
            self.assertEqual(w.sample({"kind": "crypto", "coin": "bitcoin", "currency": "brl"}), 123)
            self.assertEqual(get.call_args.args[0], "https://api.coingecko.com/api/v3/simple/price")
