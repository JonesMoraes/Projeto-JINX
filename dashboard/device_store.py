"""Private, persistent storage for phone authorizations in the JINX dashboard."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import sys
import threading
from pathlib import Path


class DeviceStoreUnavailable(RuntimeError):
    """The authorization store cannot safely read or update its records."""


class DeviceSessionStore:
    """Persist device-token hashes and protected session keys, never raw tokens."""

    _VERSION = 1
    _AAD_PREFIX = b"JINX.RemoteDevices.v1:"
    _DPAPI_ENTROPY = b"JINX.RemoteDevices.v1"

    def __init__(self, data_dir: Path | str | None = None):
        self.data_dir = Path(data_dir) if data_dir is not None else self.default_data_dir()
        self.path = self.data_dir / "remote_devices.json"
        self._key_path = self.data_dir / "remote_devices.key"
        self._lock = threading.RLock()
        self._records: dict[str, str] = {}
        self._unavailable = False
        self._load()

    @staticmethod
    def default_data_dir() -> Path:
        """Return the per-user data directory, outside the source repository."""
        if os.name == "nt":
            root = os.environ.get("LOCALAPPDATA") or str(
                Path.home() / "AppData" / "Local"
            )
            return Path(root) / "JINX" / "remote-access"
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / "JINX" / "remote-access"
        root = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        return Path(root) / "jinx" / "remote-access"

    @property
    def unavailable(self) -> bool:
        return self._unavailable

    @staticmethod
    def _digest(device_token: str) -> str:
        if not isinstance(device_token, str) or not device_token:
            raise ValueError("device token must be a non-empty string")
        return hashlib.sha256(device_token.encode("utf-8")).hexdigest()

    def _key(self) -> bytes:
        """Load/create an owner-only fallback key for non-Windows systems."""
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            self.data_dir.chmod(0o700)
        except OSError:
            pass
        try:
            fd = os.open(
                self._key_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            with os.fdopen(fd, "wb") as f:
                f.write(secrets.token_bytes(32))
                f.flush()
                os.fsync(f.fileno())
        except FileExistsError:
            pass
        key = self._key_path.read_bytes()
        if len(key) != 32:
            raise DeviceStoreUnavailable("invalid local protection key")
        return key

    def _protect(self, digest: str, session_key: str) -> str:
        payload = f"{digest}:{session_key}".encode("utf-8")
        if os.name == "nt":
            try:
                import win32crypt
                protected = win32crypt.CryptProtectData(
                    payload, "JINX remote device", self._DPAPI_ENTROPY,
                    None, None, 0,
                )
            except Exception as exc:
                raise DeviceStoreUnavailable("Windows data protection failed") from exc
            return "dpapi$" + base64.b64encode(protected).decode("ascii")

        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            nonce = secrets.token_bytes(12)
            ciphertext = AESGCM(self._key()).encrypt(
                nonce, payload, self._AAD_PREFIX + digest.encode("ascii")
            )
        except Exception as exc:
            raise DeviceStoreUnavailable("local data protection failed") from exc
        return "aesgcm$" + base64.b64encode(nonce + ciphertext).decode("ascii")

    def _unprotect(self, digest: str, sealed: str) -> str:
        try:
            kind, encoded = sealed.split("$", 1)
            ciphertext = base64.b64decode(encoded, validate=True)
            if kind == "dpapi" and os.name == "nt":
                import win32crypt
                payload = win32crypt.CryptUnprotectData(
                    ciphertext, self._DPAPI_ENTROPY, None, None, 0
                )[1]
            elif kind == "aesgcm" and os.name != "nt":
                from cryptography.hazmat.primitives.ciphers.aead import AESGCM
                nonce, body = ciphertext[:12], ciphertext[12:]
                if len(nonce) != 12 or len(body) < 16:
                    raise ValueError("truncated protected record")
                payload = AESGCM(self._key()).decrypt(
                    nonce, body, self._AAD_PREFIX + digest.encode("ascii")
                )
            else:
                raise ValueError("unsupported protected record")
            stored_digest, session_key = payload.decode("utf-8").split(":", 1)
            if stored_digest != digest or not session_key:
                raise ValueError("record identity mismatch")
            return session_key
        except Exception as exc:
            raise DeviceStoreUnavailable("authorization record cannot be verified") from exc

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if payload.get("version") != self._VERSION or not isinstance(
                payload.get("devices"), dict
            ):
                raise ValueError("unsupported authorization store")
            records = payload["devices"]
            for digest, sealed in records.items():
                if (
                    not isinstance(digest, str)
                    or len(digest) != 64
                    or any(c not in "0123456789abcdef" for c in digest)
                    or not isinstance(sealed, str)
                ):
                    raise ValueError("invalid authorization record")
                self._unprotect(digest, sealed)
            self._records = dict(records)
        except Exception:
            # Keep the original file intact; silently replacing it could erase
            # a valid device or turn a damaged store into an empty trusted one.
            self._records = {}
            self._unavailable = True

    def _write(self, records: dict[str, str]) -> None:
        if self._unavailable:
            raise DeviceStoreUnavailable("authorization store is unavailable")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        try:
            if os.name != "nt":
                self.data_dir.chmod(0o700)
        except OSError:
            pass
        body = json.dumps(
            {"version": self._VERSION, "devices": records},
            ensure_ascii=True,
            separators=(",", ":"),
        )
        temp = self.data_dir / f"remote_devices.{secrets.token_hex(8)}.tmp"
        try:
            with temp.open("x", encoding="utf-8", newline="\n") as f:
                f.write(body)
                f.flush()
                os.fsync(f.fileno())
            try:
                if os.name != "nt":
                    temp.chmod(0o600)
            except OSError:
                pass
            os.replace(temp, self.path)
            try:
                if os.name != "nt":
                    self.path.chmod(0o600)
            except OSError:
                pass
        except Exception as exc:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
            if isinstance(exc, DeviceStoreUnavailable):
                raise
            raise DeviceStoreUnavailable("authorization store could not be written") from exc

    def register(self, device_token: str, session_key: str) -> None:
        if not isinstance(session_key, str) or not session_key:
            raise ValueError("session key must be a non-empty string")
        digest = self._digest(device_token)
        with self._lock:
            if self._unavailable:
                raise DeviceStoreUnavailable("authorization store is unavailable")
            records = dict(self._records)
            records[digest] = self._protect(digest, session_key)
            self._write(records)
            self._records = records

    def resolve(self, device_token: str) -> str | None:
        try:
            digest = self._digest(device_token)
        except ValueError:
            return None
        with self._lock:
            if self._unavailable:
                return None
            sealed = self._records.get(digest)
            if sealed is None:
                return None
            try:
                return self._unprotect(digest, sealed)
            except DeviceStoreUnavailable:
                self._unavailable = True
                return None

    def remove(self, device_token: str) -> bool:
        try:
            digest = self._digest(device_token)
        except ValueError:
            return False
        with self._lock:
            if self._unavailable:
                raise DeviceStoreUnavailable("authorization store is unavailable")
            if digest not in self._records:
                return False
            records = dict(self._records)
            del records[digest]
            self._write(records)
            self._records = records
            return True

    def clear(self) -> int:
        """Explicit revoke-all also clears an unreadable store."""
        with self._lock:
            count = len(self._records)
            try:
                self.path.unlink(missing_ok=True)
                for temp in self.data_dir.glob("remote_devices.*.tmp"):
                    temp.unlink(missing_ok=True)
            except OSError as exc:
                raise DeviceStoreUnavailable("authorization store could not be cleared") from exc
            self._records = {}
            self._unavailable = False
            return count

    def __len__(self) -> int:
        return len(self._records)
