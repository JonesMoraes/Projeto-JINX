"""Resolve platform-neutral desktop intents through JINX's existing OS layer.

Skills should describe an intent (for example ``launch_app``), never branch on
Windows/macOS/Linux. Existing actions remain the sole owners of platform calls
and their verification/guardrails.
"""
from __future__ import annotations

import platform
from dataclasses import dataclass
from typing import Any

from core import outcome


@dataclass(frozen=True, slots=True)
class Backend:
    """A platform identity over JINX's shared, already-dispatched actions."""

    os_name: str

    def capabilities(self) -> dict[str, Any]:
        from core.platform_support import detect
        support = detect()
        return {"requested_backend": self.os_name, "host_os": support.os_name,
                "is_host_backend": self.os_name == support.os_name,
                "can_control_input": support.can_control_input,
                "can_capture_screen": support.can_capture_screen,
                "can_focus_windows": support.can_focus_windows,
                "notes": list(support.notes)}

    def execute(self, intent: str, **arguments: Any) -> str:
        """Execute one supported intent on this host, with existing checks."""
        if self.os_name != platform_name():
            return outcome.failed("os_adapter", "Backend does not match the current host.",
                                  requested_backend=self.os_name, host_os=platform_name())
        if intent == "launch_app":
            from actions.open_app import open_app
            return open_app({"app_name": str(arguments.get("name", ""))})
        if intent == "focus_app":
            from core.screenact import focus_app
            result = focus_app(str(arguments.get("name", "")))
            if result.ok:
                return outcome.done("os_adapter_focus", app=result.target or arguments.get("name"))
            return outcome.unverified("os_adapter_focus", result.error or "Focus was not verified.")
        return outcome.failed("os_adapter", "Unsupported desktop intent.", intent=intent)


class WindowsBackend(Backend):
    def __init__(self) -> None:
        super().__init__("Windows")


class MacOSBackend(Backend):
    def __init__(self) -> None:
        super().__init__("macOS")


class LinuxBackend(Backend):
    def __init__(self) -> None:
        super().__init__("Linux")


_BACKENDS = {"windows": WindowsBackend, "darwin": MacOSBackend,
             "macos": MacOSBackend, "linux": LinuxBackend}


def platform_name() -> str:
    """Return JINX's canonical platform label."""
    raw = platform.system()
    if raw == "Darwin":
        return "macOS"
    return raw


def get_backend(os_name: str | None = None) -> Backend:
    """Select this host's adapter, or construct a named adapter for inspection."""
    key = (os_name or platform.system()).strip().lower()
    try:
        return _BACKENDS[key]()
    except KeyError as exc:
        raise ValueError(f"unsupported operating system: {os_name or key}") from exc
