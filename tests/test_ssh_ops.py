import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from actions import ssh_ops


class SSHOpsTests(unittest.TestCase):
    def test_unknown_hosts_are_rejected_by_default(self):
        client = MagicMock()
        client.connect.side_effect = RuntimeError("unknown host key")
        paramiko = MagicMock()
        paramiko.SSHClient.return_value = client
        with patch.dict("sys.modules", {"paramiko": paramiko}):
            result = ssh_ops.ssh_ops({"action": "probe", "host": "server.example", "username": "me"})
        self.assertIn("status=failed", result)
        client.set_missing_host_key_policy.assert_not_called()
        client.close.assert_called_once()

    def test_exec_returns_remote_exit_status_and_output(self):
        client = MagicMock()
        transport = MagicMock()
        transport.is_active.return_value = True
        client.get_transport.return_value = transport
        stdout = MagicMock()
        stdout.read.return_value = b"ok\n"
        stdout.channel.recv_exit_status.return_value = 0
        stderr = MagicMock()
        stderr.read.return_value = b""
        client.exec_command.return_value = (None, stdout, stderr)
        with patch("actions.ssh_ops._connect", return_value=client):
            result = ssh_ops.ssh_ops({"action": "exec", "host": "host", "username": "me",
                                      "command": "echo ok"})
        self.assertIn("status=done", result)
        self.assertIn("verified=true", result)
        client.close.assert_called_once()

    def test_deploy_verifies_remote_size(self):
        with tempfile.TemporaryDirectory() as folder:
            local = Path(folder) / "payload.txt"
            local.write_text("payload", encoding="utf-8")
            client = MagicMock()
            transport = MagicMock()
            transport.is_active.return_value = True
            client.get_transport.return_value = transport
            sftp = MagicMock()
            sftp.stat.return_value.st_size = local.stat().st_size
            client.open_sftp.return_value = sftp
            with patch("actions.ssh_ops._connect", return_value=client):
                result = ssh_ops.ssh_ops({"action": "deploy", "host": "host", "username": "me",
                                          "local_path": str(local), "remote_path": "/tmp/payload.txt"})
            self.assertIn("status=done", result)
            sftp.close.assert_called_once()
            client.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
