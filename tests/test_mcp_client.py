import asyncio
import os
from pathlib import Path
import sys
import tempfile
import unittest

from core.mcp_client import MCPConnector, config_from_settings


class MCPConfigTests(unittest.TestCase):
    def test_requires_secure_remote_http(self):
        values = {"server_name": "remote", "transport": "http", "url": "http://example.com/mcp"}
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            config_from_settings(values)

    def test_allows_local_http_and_parses_stdio(self):
        cfg = config_from_settings({"server_name": "local", "transport": "http", "url": "http://localhost:8000/mcp"})
        self.assertEqual(cfg.url, "http://localhost:8000/mcp")
        cfg = config_from_settings({"server_name": "local", "command": sys.executable,
                                    "stdio_args": '["server.py"]', "env_names": '["PATH"]'})
        self.assertEqual(cfg.args, ("server.py",))
        self.assertEqual(cfg.env_names, ("PATH",))

    def test_rejects_invalid_config_json(self):
        with self.assertRaisesRegex(ValueError, "JSON arrays"):
            config_from_settings({"server_name": "local", "command": "python", "stdio_args": "oops"})


class MCPStdioIntegrationTests(unittest.TestCase):
    def test_connects_to_external_stdio_server_and_calls_tool(self):
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / "fixture_server.py"
            script.write_text(
                "from mcp.server.mcpserver import MCPServer\n"
                "import asyncio\n"
                "server = MCPServer('fixture', version='1.0')\n"
                "@server.tool()\n"
                "def echo(text: str) -> str:\n"
                "    return text\n"
                "asyncio.run(server.run_stdio_async())\n",
                encoding="utf-8",
            )
            cfg = config_from_settings({"server_name": "fixture", "command": sys.executable,
                                        "stdio_args": __import__("json").dumps([str(script)]),
                                        "cwd": folder})
            connector = MCPConnector(cfg)
            tools = asyncio.run(connector.list_tools())
            self.assertIn("echo", [tool["name"] for tool in tools])
            result = asyncio.run(connector.call_tool("echo", {"text": "JINX MCP ready"}))
            self.assertFalse(result.get("isError", False))
            self.assertIn("JINX MCP ready", str(result))


if __name__ == "__main__":
    unittest.main()
