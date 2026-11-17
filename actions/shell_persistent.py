"""Tool interface for persistent, parallel local shell sessions."""
from __future__ import annotations

import json

from core import outcome
from core.persistent_shell import _DEFAULT

TOOL = {
    "name": "shell_persistent",
    "description": "Start, list, execute commands in, or close persistent local PowerShell/bash/zsh sessions. Session variables and current directory persist; separate sessions run in parallel.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["start", "exec", "list", "close"]},
            "session_id": {"type": "STRING"},
            "command": {"type": "STRING"},
            "cwd": {"type": "STRING"},
            "timeout_seconds": {"type": "INTEGER"},
        },
        "required": ["action"],
    },
    "handler": None,
    "tier": "core",
    "brief": "Manage persistent local shell sessions.",
}


def shell_persistent(parameters: dict, **_context) -> str:
    p = parameters or {}
    action = str(p.get("action", "")).lower()
    try:
        if action == "start":
            session_id = _DEFAULT.start(p.get("cwd"))
            return outcome.done("shell_start", session_id=session_id,
                                shell=_DEFAULT.list()[-1]["shell"])
        if action == "list":
            return outcome.done("shell_list", sessions=json.dumps(_DEFAULT.list()))
        session_id = str(p.get("session_id", ""))
        if action == "exec":
            return _DEFAULT.execute(session_id, p.get("command", ""),
                                    p.get("timeout_seconds", 60))
        if action == "close":
            if _DEFAULT.close(session_id):
                return outcome.done("shell_close", session_id=session_id)
            return outcome.failed("shell_close", "Unknown shell session.", session_id=session_id)
        return outcome.failed("shell_persistent", "Unsupported action.", action=action)
    except (OSError, ValueError, RuntimeError) as exc:
        return outcome.failed("shell_persistent", str(exc))


TOOL["handler"] = shell_persistent
