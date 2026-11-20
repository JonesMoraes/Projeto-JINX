"""Episodic memory: redaction BEFORE storage, exclusion, bounded rotation.

Nothing here may store a secret-shaped string; excluded windows must never be
written; captures live in bounded day folders and forget() actually deletes.
"""
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from memory import episodic


def _cfg(**overrides):
    # Owner defaults: observation ON, screen ON — matches episodic._cfg().
    base = {"enabled": True, "screen": True, "interval": 60.0, "keep_days": 7,
            "exclude": episodic._DEFAULT_EXCLUDE.pattern}
    base.update(overrides)
    return base


class EpisodicTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        episodic.DB_PATH = root / "episodic.db"
        episodic.CAPTURE_DIR = root / "captures"
        self.cfg = _cfg()
        self.cfg_patch = patch.object(episodic, "_cfg", side_effect=lambda: dict(self.cfg))
        self.save_patch = patch.object(episodic, "save_plugin_config", lambda ns, values: None)
        self.cfg_patch.start(); self.save_patch.start()
        self.addCleanup(self.cfg_patch.stop); self.addCleanup(self.save_patch.stop)

    def _read(self, sql, args=()):
        # sqlite3.connect as a `with` does NOT close on Windows — always closing().
        with closing(sqlite3.connect(episodic.DB_PATH)) as db:
            return db.execute(sql, args).fetchall()

    def _exec(self, sql, args=()):
        with closing(sqlite3.connect(episodic.DB_PATH)) as db, db:
            db.execute(sql, args)

    def test_first_run_ships_on_and_explicit_off_wins(self):
        """Owner decision: observation (screen included) ships ON via the module
        defaults; an explicit False in the saved config always wins over them."""
        # Drop the per-test _cfg patch to exercise the real default plumbing.
        self.cfg_patch.stop()
        try:
            with patch.object(episodic, "get_plugin_config", return_value={}):
                first_run = episodic._cfg()
            self.assertTrue(first_run["enabled"],
                            "primeira execução (config vazia) deve nascer ligada")
            self.assertTrue(first_run["screen"])
            with patch.object(episodic, "get_plugin_config",
                              return_value={"enabled": False, "screen": False}):
                turned_off = episodic._cfg()
            self.assertFalse(turned_off["enabled"])
            self.assertFalse(turned_off["screen"])
        finally:
            self.cfg_patch.start()  # restore the standard patch for other tests

    def test_secrets_are_redacted_before_storage(self):
        episodic.note_tool("action", "shell_persistent",
                           "set OPENAI_API_KEY=sk-aaaaaaaaaaaaaaaaaaaaaaaaaaa1234")
        detail = self._read("SELECT detail FROM events ORDER BY id DESC LIMIT 1")[0][0]
        self.assertNotIn("sk-", detail)
        self.assertIn("[REDACTED]", detail)

    def test_excluded_windows_never_reach_the_store(self):
        episodic.note_window("1Password", "Cofre principal")
        episodic.note_window("Bradesco", "Internet Banking")
        episodic.note_window("Chrome", "Como fazer café")
        apps = {r[0] for r in self._read("SELECT app FROM events")}
        self.assertIn("Chrome", apps)
        self.assertNotIn("1Password", apps)
        self.assertNotIn("Bradesco", apps)

    def test_recall_returns_only_when_it_has_signal(self):
        episodic.note_window("Excel", "planilha-de-vendas.xlsx")
        episodic.note_tool("action", "file_controller", "done")
        result = episodic.recall("planilha de vendas", k=3)
        self.assertIn("MEMÓRIA OBSERVADA", result)
        self.assertIn("vendas", result)
        self.assertEqual(episodic.recall("assunto-completamente-estranho-xyz", k=3),
                         "Nada parecido encontrado no que foi observado.")

    def test_forget_deletes_old_and_keeps_recent_with_captures_rotating(self):
        episodic.note_window("Chrome", "fresco de agora")
        old_ts = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        self._exec("INSERT INTO events(ts,kind,app,title,detail) VALUES(?,?,?,?,?)",
                   (old_ts, "window", "Excel", "antigo", ""))
        result = episodic.forget(days=1)
        self.assertIn("Esquecidos", result)
        apps = {r[0] for r in self._read("SELECT app FROM events")}
        self.assertEqual(apps, {"Chrome"},
                         "o antigo (>N dias) sai; o observado agora fica")

    def test_digest_writes_one_episode_for_the_day(self):
        episodic.note_window("Chrome", "site A")
        episodic.note_window("Excel", "planilha")
        result = episodic.digest()
        self.assertIn("Episódio", result)
        rows = self._read("SELECT day,text FROM episodes")
        self.assertEqual(len(rows), 1)
        self.assertIn("Chrome", rows[0][1])


if __name__ == "__main__":
    unittest.main()
