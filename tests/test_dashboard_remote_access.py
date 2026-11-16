import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from dashboard.device_store import DeviceSessionStore, DeviceStoreUnavailable
from dashboard.server import DashboardServer


class DeviceSessionStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_round_trip_keeps_only_hash_and_protected_session_key(self):
        token = "device-token-that-must-not-be-saved"
        session_key = "A7K9M2Q5"
        store = DeviceSessionStore(self.root)

        store.register(token, session_key)

        raw = (self.root / "remote_devices.json").read_text(encoding="utf-8")
        self.assertNotIn(token, raw)
        self.assertNotIn(session_key, raw)
        self.assertIn("version", json.loads(raw))
        if os.name != "nt":
            self.assertEqual(
                (self.root / "remote_devices.key").stat().st_mode & 0o777,
                0o600,
            )
        reopened = DeviceSessionStore(self.root)
        self.assertEqual(reopened.resolve(token), session_key)
        self.assertIsNone(reopened.resolve("unknown-device-token"))

    def test_remove_and_clear_revoke_durable_authorizations(self):
        store = DeviceSessionStore(self.root)
        store.register("phone-a", "A7K9M2Q5")
        store.register("phone-b", "D8R4T6V2")

        self.assertTrue(store.remove("phone-a"))
        self.assertIsNone(DeviceSessionStore(self.root).resolve("phone-a"))
        self.assertEqual(DeviceSessionStore(self.root).resolve("phone-b"), "D8R4T6V2")
        self.assertEqual(store.clear(), 1)
        self.assertIsNone(DeviceSessionStore(self.root).resolve("phone-b"))

    def test_corrupt_store_fails_closed_and_preserves_original_file(self):
        path = self.root / "remote_devices.json"
        path.write_text("{truncated", encoding="utf-8")
        store = DeviceSessionStore(self.root)

        self.assertIsNone(store.resolve("any-device"))
        with self.assertRaises(DeviceStoreUnavailable):
            store.register("new-device", "A7K9M2Q5")
        self.assertEqual(path.read_text(encoding="utf-8"), "{truncated")
        self.assertEqual(store.clear(), 0)  # explicit revoke-all may clear corruption
        self.assertFalse(path.exists())


class DashboardDeviceAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _server(self):
        store = DeviceSessionStore(self.root)
        server = DashboardServer(device_store=store)
        self.assertIs(server._device_store, store)
        return server

    def test_remembered_manual_login_survives_server_restart(self):
        first = self._server()
        key = first.new_key()
        with TestClient(first.app) as client:
            login = client.post("/login", json={"pin": key, "remember": True})
            self.assertEqual(login.status_code, 200)
            payload = login.json()
            self.assertTrue(payload["ok"])
            self.assertTrue(payload.get("device_token"))

        restarted = self._server()
        with TestClient(restarted.app) as client:
            refreshed = client.post(
                "/api/device-login",
                json={"device_token": payload["device_token"]},
            )
            self.assertEqual(refreshed.status_code, 200)
            self.assertTrue(refreshed.json()["ok"])
            self.assertEqual(refreshed.json()["key"], key)

    def test_manual_login_without_remember_does_not_create_device_token(self):
        server = self._server()
        with TestClient(server.app) as client:
            response = client.post(
                "/login", json={"pin": server.new_key(), "remember": False}
            )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("device_token", response.json())
        self.assertEqual(len(DeviceSessionStore(self.root)), 0)

    def test_device_login_rejects_malformed_device_token_without_server_error(self):
        server = self._server()
        with TestClient(server.app) as client:
            response = client.post("/api/device-login", json={"device_token": 42})
        self.assertEqual(response.status_code, 401)

    def test_qr_pairing_survives_server_restart(self):
        first = self._server()
        key = first.new_key()
        with TestClient(first.app) as client:
            page = client.get("/auto-login", params={"key": key})
            self.assertEqual(page.status_code, 200)
            match = re.search(
                r"localStorage\.setItem\('jinx_device_token','([^']+)'\)",
                page.text,
            )
            self.assertIsNotNone(match)
            device_token = match.group(1)

        restarted = self._server()
        with TestClient(restarted.app) as client:
            response = client.post(
                "/api/device-login", json={"device_token": device_token}
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["key"], key)

    def test_logout_unpairs_device_persistently(self):
        server = self._server()
        with TestClient(server.app) as client:
            login = client.post(
                "/login", json={"pin": server.new_key(), "remember": True}
            ).json()
            headers = {"Authorization": f"Bearer {login['token']}"}
            unpaired = client.post(
                "/api/device-unpair",
                headers=headers,
                json={"device_token": login["device_token"]},
            )
            self.assertEqual(unpaired.status_code, 200)
            self.assertTrue(unpaired.json()["unpaired"])
            denied = client.post(
                "/api/device-login",
                json={"device_token": login["device_token"]},
            )
            self.assertEqual(denied.status_code, 401)

        restarted = self._server()
        with TestClient(restarted.app) as client:
            denied_after_restart = client.post(
                "/api/device-login",
                json={"device_token": login["device_token"]},
            )
        self.assertEqual(denied_after_restart.status_code, 401)

    def test_revoke_all_clears_persistent_devices_and_live_sessions(self):
        server = self._server()
        with TestClient(server.app) as client:
            first = client.post(
                "/login", json={"pin": server.new_key(), "remember": True}
            ).json()
            second = client.post(
                "/login", json={"pin": server.new_key(), "remember": True}
            ).json()
            response = client.post(
                "/api/revoke-devices",
                headers={"Authorization": f"Bearer {first['token']}"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["revoked"], 2)
            self.assertEqual(response.json()["sessions_ended"], 1)
            self.assertEqual(
                client.post(
                    "/api/device-login",
                    json={"device_token": second["device_token"]},
                ).status_code,
                401,
            )
            self.assertEqual(
                client.post(
                    "/api/command",
                    headers={"Authorization": f"Bearer {second['token']}"},
                    json={"text": "ignored"},
                ).status_code,
                401,
            )

        restarted = self._server()
        with TestClient(restarted.app) as client:
            self.assertEqual(
                client.post(
                    "/api/device-login",
                    json={"device_token": first["device_token"]},
                ).status_code,
                401,
            )

    def test_login_rejects_remembered_authorization_when_store_is_corrupt(self):
        path = self.root / "remote_devices.json"
        path.write_text("{truncated", encoding="utf-8")
        server = self._server()
        with TestClient(server.app) as client:
            response = client.post(
                "/login", json={"pin": server.new_key(), "remember": True}
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(path.read_text(encoding="utf-8"), "{truncated")


class MobileRemoteShellTests(unittest.TestCase):
    def test_login_accepts_eight_characters_and_offers_explicit_remember(self):
        root = Path(__file__).resolve().parents[1] / "dashboard" / "static"
        html = (root / "login.html").read_text(encoding="utf-8")
        self.assertIn('maxlength="8"', html)
        self.assertIn('id="remember-device"', html)
        self.assertIn("remember:", html)
        self.assertIn("r.status === 401", html)

    def test_mobile_shell_preserves_actions_and_handles_safe_viewports(self):
        root = Path(__file__).resolve().parents[1] / "dashboard" / "static"
        html = (root / "app.html").read_text(encoding="utf-8")
        for contract in (
            "revokeRemoteDevices", "logoutRemote", "device-unpair",
            "100dvh", "safe-area-inset-bottom", "prefers-reduced-motion",
            "doMic", "doSend", "doWake", "file-inp",
        ):
            self.assertIn(contract, html)


if __name__ == "__main__":
    unittest.main()
