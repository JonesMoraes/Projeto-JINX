from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import audit


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {"JINX_AUDIT_DB": str(Path(self.temp.name) / "audit.db")})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_records_call_metadata_and_redacts_credentials_and_payloads(self):
        self.assertTrue(audit.record_tool_call(
            "action", "example", {"api_key": "do-not-store", "text": "private words",
                                    "command": "echo confidential",
                                    "target": "file.txt"},
            "status=done action=example result=private", 12.5))
        rows = audit.recent()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["outcome"], "done")
        self.assertAlmostEqual(rows[0]["duration_ms"], 12.5)
        args = json.loads(rows[0]["parameters_json"])
        self.assertEqual(args["api_key"], "[REDACTED]")
        self.assertEqual(args["text"], "[OMITTED 13 chars]")
        self.assertEqual(args["command"], "[OMITTED 17 chars]")
        self.assertNotIn("private", rows[0]["parameters_json"])

    def test_unknown_status_and_limit_are_normalized(self):
        audit.record_tool_call("plugin", "noop", {}, "plain response", -10)
        rows = audit.recent(10000)
        self.assertEqual(rows[0]["outcome"], "unknown")
        self.assertEqual(rows[0]["duration_ms"], 0)


if __name__ == "__main__":
    unittest.main()
