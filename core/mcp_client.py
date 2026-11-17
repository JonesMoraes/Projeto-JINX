"""Official MCP SDK client wrapper for stdio and Streamable HTTP servers."""
from __future__ import annotations

import json
import os
import re
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class MCPServerConfig:
    name: str
    transport: str
    command: str = ""
    args: tuple[str, ...] = ()
    cwd: str = ""
    url: str = ""
    env_names: tuple[str, ...] = ()
    bearer_token_env: str = ""


def config_from_settings(values: dict[str, Any]) -> MCPServerConfig:
    values = values or {}
    name = str(values.get("server_name", "")).strip()
    transport = str(values.get("transport", "stdio")).strip().lower()
    if not name or len(name) > 80:
        raise ValueError("Set a short server name in MCP Client settings.")
    if transport not in {"stdio", "http"}:
        raise ValueError("transport must be stdio or http")
    try:
        args = json.loads(str(values.get("stdio_args", "[]") or "[]"))
        env_names = json.loads(str(values.get("env_names", "[]") or "[]"))
    except json.JSONDecodeError as exc:
        raise ValueError("stdio_args and env_names must be JSON arrays") from exc
    if not isinstance(args, list) or len(args) > 64 or not all(isinstance(x, str) for x in args):
        raise ValueError("stdio_args must be an array of up to 64 strings")
    if not isinstance(env_names, list) or len(env_names) > 32 or not all(
            isinstance(x, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", x) for x in env_names):
        raise ValueError("env_names must be an array of environment variable names")
    cwd = str(values.get("cwd", "")).strip()
    if cwd and not Path(cwd).expanduser().is_dir():
        raise ValueError("stdio working directory does not exist")
    token_env = str(values.get("bearer_token_env", "")).strip()
    if token_env and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token_env):
        raise ValueError("bearer_token_env must be an environment variable name")
    command = str(values.get("command", "")).strip()
    url = str(values.get("url", "")).strip()
    if transport == "stdio" and not command:
        raise ValueError("stdio command is required")
    if transport == "http":
        parsed = urlsplit(url)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname:
            raise ValueError("MCP URL must be an absolute http(s) URL")
        loopback = parsed.hostname.casefold() in {"localhost", "127.0.0.1", "::1"}
        if parsed.scheme != "https" and not loopback:
            raise ValueError("remote MCP servers must use HTTPS")
    return MCPServerConfig(name, transport, command, tuple(args), cwd, url,
                           tuple(env_names), token_env)


class MCPConnector:
    """Thin async client; creates and closes an SDK connection per operation."""

    def __init__(self, config: MCPServerConfig | Any):
        self.config = config

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[Any]:
        from mcp.client import Client
        cfg = self.config
        if not isinstance(cfg, MCPServerConfig):
            async with Client(cfg) as client:
                yield client
            return
        if cfg.transport == "stdio":
            from mcp.client.stdio import StdioServerParameters
            env = {key: os.environ[key] for key in cfg.env_names if key in os.environ}
            server = StdioServerParameters(command=cfg.command, args=list(cfg.args),
                                           env=env, cwd=cfg.cwd or None,
                                           encoding_error_handler="replace")
            async with Client(server) as client:
                yield client
            return

        headers = {}
        if cfg.bearer_token_env:
            token = os.environ.get(cfg.bearer_token_env, "")
            if not token:
                raise ValueError(f"Environment variable {cfg.bearer_token_env} is not set")
            headers["Authorization"] = f"Bearer {token}"
        if headers:
            import httpx2
            from mcp.client.streamable_http import streamable_http_client
            async with AsyncExitStack() as stack:
                http_client = await stack.enter_async_context(httpx2.AsyncClient(
                    headers=headers,
                    timeout=httpx2.Timeout(30.0, read=300.0),
                ))
                transport = streamable_http_client(cfg.url, http_client=http_client)
                client = await stack.enter_async_context(Client(transport))
                yield client
        else:
            async with Client(cfg.url) as client:
                yield client

    async def list_tools(self) -> list[dict[str, Any]]:
        async with self._connect() as client:
            result = await client.list_tools()
            return [tool.model_dump(mode="json", exclude_none=True) for tool in result.tools]

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        async with self._connect() as client:
            result = await client.call_tool(name, arguments or {})
            return result.model_dump(mode="json", exclude_none=True)

    async def list_resources(self) -> list[dict[str, Any]]:
        async with self._connect() as client:
            result = await client.list_resources()
            return [item.model_dump(mode="json", exclude_none=True) for item in result.resources]

    async def read_resource(self, uri: str) -> dict[str, Any]:
        async with self._connect() as client:
            result = await client.read_resource(uri)
            return result.model_dump(mode="json", exclude_none=True)

    async def list_prompts(self) -> list[dict[str, Any]]:
        async with self._connect() as client:
            result = await client.list_prompts()
            return [item.model_dump(mode="json", exclude_none=True) for item in result.prompts]

    async def get_prompt(self, name: str, arguments: dict[str, str] | None = None) -> dict[str, Any]:
        async with self._connect() as client:
            result = await client.get_prompt(name, arguments or {})
            return result.model_dump(mode="json", exclude_none=True)
