"""SSH operations with strict host-key checking and environment-only passwords."""
from __future__ import annotations

import os
import re
from pathlib import Path

from core import outcome


def _connect(p):
    import paramiko

    host = str(p.get("host") or "").strip()
    username = str(p.get("username") or "").strip()
    if not host or not username or len(host) > 253 or not re.fullmatch(r"[A-Za-z0-9.-]+", host):
        raise ValueError("A valid SSH host and username are required.")
    port = int(p.get("port", 22))
    if not 1 <= port <= 65535:
        raise ValueError("SSH port must be between 1 and 65535.")
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    known_hosts = str(p.get("known_hosts") or "").strip()
    if known_hosts:
        client.load_host_keys(str(Path(known_hosts).expanduser()))
    # Unknown host keys are refused; this intentionally never uses AutoAddPolicy.
    password_env = str(p.get("password_env") or "").strip()
    password = os.environ.get(password_env) if password_env else None
    key_file = str(p.get("key_file") or "").strip()
    try:
        client.connect(hostname=host, port=port, username=username, password=password,
                       key_filename=str(Path(key_file).expanduser()) if key_file else None,
                       timeout=max(2, min(int(p.get("timeout_seconds", 15)), 60)),
                       banner_timeout=15, auth_timeout=15, allow_agent=True,
                       look_for_keys=not bool(key_file or password))
    except Exception:
        client.close()
        raise
    return client


def ssh_ops(parameters: dict, **_context) -> str:
    p = parameters or {}
    action = str(p.get("action", "")).lower()
    if action not in {"probe", "exec", "deploy", "download"}:
        return outcome.failed("ssh_ops", "Unsupported SSH action.")
    client = None
    try:
        client = _connect(p)
        transport = client.get_transport()
        if not transport or not transport.is_active():
            return outcome.failed("ssh_ops", "SSH transport is not active.")
        if action == "probe":
            return outcome.done("ssh_ops", host=p.get("host"), authenticated=True,
                                host_key_verified=True)
        if action == "exec":
            command = str(p.get("command") or "")
            if not command or len(command) > 20_000:
                raise ValueError("Remote command is empty or too long.")
            _stdin, stdout, stderr = client.exec_command(command, timeout=max(2, min(int(p.get("timeout_seconds", 30)), 300)))
            out, err = stdout.read(1_000_000), stderr.read(200_000)
            code = stdout.channel.recv_exit_status()
            return outcome.done("ssh_exec", host=p.get("host"), exit_code=code,
                                stdout=out.decode("utf-8", "replace"),
                                stderr=err.decode("utf-8", "replace"),
                                verified=code == 0)
        local_input = Path(str(p.get("local_path") or "")).expanduser()
        if local_input.is_symlink():
            raise ValueError("Symbolic-link local files are not accepted.")
        local = local_input.resolve(strict=True)
        remote = str(p.get("remote_path") or "").strip()
        if not local.is_file() or local.is_symlink() or not remote.startswith("/") or "\x00" in remote:
            raise ValueError("Use a regular local file and an absolute remote path.")
        sftp = client.open_sftp()
        try:
            if action == "deploy":
                sftp.put(str(local), remote)
                verified = sftp.stat(remote).st_size == local.stat().st_size
                if not verified:
                    return outcome.unverified("ssh_deploy", "Remote file size did not match.",
                                              host=p.get("host"), remote_path=remote)
                return outcome.done("ssh_deploy", host=p.get("host"), remote_path=remote,
                                    bytes=local.stat().st_size, verified=True)
            target = Path(str(p.get("download_path") or "")).expanduser().absolute()
            if not str(p.get("download_path") or "").strip() or target.exists():
                raise ValueError("Download destination is required and must not exist.")
            sftp.get(remote, str(target))
            if not target.is_file() or target.stat().st_size != sftp.stat(remote).st_size:
                target.unlink(missing_ok=True)
                return outcome.failed("ssh_download", "Downloaded file failed size verification.")
            return outcome.done("ssh_download", host=p.get("host"), local_path=str(target),
                                bytes=target.stat().st_size, verified=True)
        finally:
            sftp.close()
    except Exception as exc:
        return outcome.failed("ssh_ops", f"SSH operation failed: {type(exc).__name__}: {str(exc)[:240]}",
                              host=p.get("host"))
    finally:
        if client is not None:
            client.close()


TOOL = {"name": "ssh_ops", "description": "Connect to a user-configured SSH host, verify its host key, run a remote command, deploy a local file over SFTP, or download a remote file. Unknown host keys are rejected. Use a key file or password environment variable; never provide credentials in the command.",
        "parameters": {"type": "OBJECT", "properties": {
            "action": {"type": "STRING", "enum": ["probe", "exec", "deploy", "download"]},
            "host": {"type": "STRING"}, "port": {"type": "INTEGER"},
            "username": {"type": "STRING"}, "known_hosts": {"type": "STRING"},
            "key_file": {"type": "STRING"}, "password_env": {"type": "STRING"},
            "command": {"type": "STRING"}, "local_path": {"type": "STRING"},
            "remote_path": {"type": "STRING"}, "download_path": {"type": "STRING"},
            "timeout_seconds": {"type": "INTEGER"}}, "required": ["action", "host", "username"]},
        "handler": ssh_ops, "tier": "extra", "brief": "Verified SSH command and file transfer."}
