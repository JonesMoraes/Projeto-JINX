"""Bounded, stateful local shell sessions for Windows, macOS, and Linux."""
from __future__ import annotations

import os
import platform
import queue
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from core import outcome

_MAX_SESSIONS = 8
_MAX_OUTPUT = 1_000_000


@dataclass
class ShellSession:
    id: str
    process: subprocess.Popen
    shell: str
    cwd: str
    output: queue.Queue = field(default_factory=queue.Queue)
    lock: threading.Lock = field(default_factory=threading.Lock)
    reader: threading.Thread | None = None

    def __post_init__(self) -> None:
        self.reader = threading.Thread(target=self._read_output,
                                       name=f"jinx-shell-{self.id[:8]}", daemon=True)
        self.reader.start()

    def _read_output(self) -> None:
        try:
            for line in self.process.stdout:
                self.output.put(line)
        except (OSError, ValueError):
            pass

    def execute(self, command: str, timeout: float) -> tuple[str, int]:
        marker = "__JINX_END_" + uuid.uuid4().hex + "__"
        if self.process.poll() is not None:
            raise RuntimeError("shell process has exited")
        if self.shell == "powershell":
            script = (command + "\n$__jinx_ok = $?\n$__jinx_code = if ($__jinx_ok) { 0 } else { 1 }\n"
                      f"[Console]::Out.WriteLine('{marker}:' + $__jinx_code)\n")
        else:
            script = (command + "\nprintf '\\n%s:%s\\n' '" + marker + "' \"$?\"\n")
        with self.lock:
            self.process.stdin.write(script)
            self.process.stdin.flush()
            chunks: list[str] = []
            size = 0
            deadline = time.monotonic() + timeout
            exit_code = 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("shell command exceeded its timeout")
                try:
                    line = self.output.get(timeout=min(remaining, 0.2))
                except queue.Empty:
                    if self.process.poll() is not None:
                        raise RuntimeError("shell process exited before returning a result") from None
                    continue
                text = line.rstrip("\r\n")
                if text.startswith(marker + ":"):
                    try:
                        exit_code = int(text.partition(":")[2])
                    except ValueError:
                        exit_code = 1
                    break
                encoded_size = len(line.encode("utf-8", errors="replace"))
                if size < _MAX_OUTPUT:
                    chunks.append(line[:max(0, _MAX_OUTPUT - size)])
                    size += encoded_size
            output = "".join(chunks)
            if size > _MAX_OUTPUT:
                output += "\n[output truncated at 1 MiB]"
            return output, exit_code


class PersistentShell:
    """Owns multiple isolated persistent shells; each session serializes commands."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: dict[str, ShellSession] = {}

    @staticmethod
    def _command(cwd: str | None = None) -> tuple[list[str], str]:
        system = platform.system()
        if system == "Windows":
            shell = shutil.which("pwsh") or shutil.which("powershell")
            if not shell:
                raise RuntimeError("PowerShell was not found")
            return [shell, "-NoLogo", "-NoProfile", "-NoExit", "-Command", "-"], "powershell"
        if system == "Darwin":
            shell = shutil.which("zsh") or "/bin/zsh"
            return [shell, "-f"], "zsh"
        if system == "Linux":
            shell = shutil.which("bash") or "/bin/bash"
            return [shell, "--noprofile", "--norc"], "bash"
        raise RuntimeError(f"unsupported operating system: {system}")

    def start(self, cwd: str | None = None, env: dict[str, str] | None = None) -> str:
        directory = Path(cwd or Path.home()).expanduser().resolve(strict=True)
        if not directory.is_dir():
            raise ValueError("cwd must be an existing directory")
        with self._lock:
            if len(self._sessions) >= _MAX_SESSIONS:
                raise RuntimeError(f"maximum of {_MAX_SESSIONS} shell sessions reached")
            argv, shell = self._command()
            session_id = uuid.uuid4().hex[:12]
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
            process = subprocess.Popen(
                argv, cwd=directory, env={**os.environ, **(env or {})}, shell=False,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
                creationflags=creationflags)
            session = ShellSession(session_id, process, shell, str(directory))
            self._sessions[session_id] = session
            return session_id

    def execute(self, session_id: str, command: str, timeout: float = 60) -> str:
        with self._lock:
            session = self._sessions.get(str(session_id))
        if session is None:
            return outcome.failed("shell_exec", "Unknown shell session.", session_id=session_id)
        command = str(command or "")
        if not command.strip() or len(command) > 100_000:
            return outcome.failed("shell_exec", "Command is empty or exceeds 100,000 characters.")
        timeout = max(1.0, min(float(timeout), 600.0))
        try:
            output, code = session.execute(command, timeout)
            return outcome.done("shell_exec", session_id=session.id, exit_code=code,
                                output=output, cwd=session.cwd)
        except TimeoutError:
            self.close(session.id, force=True)
            return outcome.failed("shell_exec", "Command timed out; session was closed.",
                                  session_id=session.id, timeout_s=timeout)
        except Exception as exc:
            self.close(session.id, force=True)
            return outcome.failed("shell_exec", str(exc), session_id=session.id)

    def list(self) -> list[dict[str, str]]:
        with self._lock:
            return [{"session_id": row.id, "shell": row.shell, "cwd": row.cwd,
                     "running": str(row.process.poll() is None).lower()}
                    for row in self._sessions.values()]

    def close(self, session_id: str, force: bool = False) -> bool:
        with self._lock:
            session = self._sessions.pop(str(session_id), None)
        if session is None:
            return False
        process = session.process
        try:
            if process.poll() is None:
                if not force and process.stdin:
                    process.stdin.write("exit\n")
                    process.stdin.flush()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.terminate()
                else:
                    process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
        finally:
            for stream in (process.stdin, process.stdout):
                try:
                    if stream:
                        stream.close()
                except OSError:
                    pass
        return True

    def close_all(self) -> None:
        with self._lock:
            session_ids = tuple(self._sessions)
        for session_id in session_ids:
            self.close(session_id, force=True)


_DEFAULT = PersistentShell()
