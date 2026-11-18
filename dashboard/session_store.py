"""Persistent session storage for JINX dashboard with encryption."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import sys
import threading
import time
from pathlib import Path
from typing import Any


class SessionStoreUnavailable(RuntimeError):
    """The session store cannot safely read or update its records."""


class SessionStore:
    """Persist dashboard sessions with encryption, never raw tokens."""

    _VERSION = 1
    _AAD_PREFIX = b"JINX.DashboardSessions.v1:"
    _DPAPI_ENTROPY = b"JINX.DashboardSessions.v1"
    _SESSION_TIMEOUT = 12 * 60 * 60  # 12 hours in seconds

    def __init__(self, data_dir: Path | str | None = None):
        self.data_dir = Path(data_dir) if data_dir is not None else self.default_data_dir()
        self.path = self.data_dir / "dashboard_sessions.json"
        self._key_path = self.data_dir / "dashboard_sessions.key"
        self._lock = threading.RLock()
        self._sessions: dict[str, dict[str, Any]] = {}
        self._unavailable = False
        self._load()

    @staticmethod
    def default_data_dir() -> Path:
        """Return the per-user data directory, outside the source repository."""
        if os.name == "nt":
            root = os.environ.get("LOCALAPPDATA") or str(
                Path.home() / "AppData" / "Local"
            )
            return Path(root) / "JINX" / "dashboard"
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / "JINX" / "dashboard"
        root = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        return Path(root) / "jinx" / "dashboard"

    @property
    def unavailable(self) -> bool:
        return self._unavailable

    @staticmethod
    def _digest(token: str) -> str:
        if not isinstance(token, str) or not token:
            raise ValueError("token must be a non-empty string")
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

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
            raise SessionStoreUnavailable("invalid local protection key")
        return key

    def _protect(self, data: dict[str, Any]) -> str:
        """Encrypt session data."""
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        token_digest = self._digest(data.get("token", ""))
        
        if os.name == "nt":
            try:
                import win32crypt
                protected = win32crypt.CryptProtectData(
                    payload, "JINX dashboard session", self._DPAPI_ENTROPY,
                    None, None, 0,
                )
            except Exception as exc:
                raise SessionStoreUnavailable("Windows data protection failed") from exc
            return "dpapi$" + base64.b64encode(protected).decode("ascii")

        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            nonce = secrets.token_bytes(12)
            ciphertext = AESGCM(self._key()).encrypt(
                nonce, payload, self._AAD_PREFIX + token_digest.encode("ascii")
            )
        except Exception as exc:
            raise SessionStoreUnavailable("local data protection failed") from exc
        return "aesgcm$" + base64.b64encode(nonce + ciphertext).decode("ascii")

    def _unprotect(self, token_digest: str, sealed: str) -> dict[str, Any]:
        """Decrypt session data."""
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
                    nonce, body, self._AAD_PREFIX + token_digest.encode("ascii")
                )
            else:
                raise ValueError("unsupported protected record")
            data = json.loads(payload.decode("utf-8"))
            if data.get("token_digest") != token_digest:
                raise ValueError("record identity mismatch")
            return data
        except Exception as exc:
            raise SessionStoreUnavailable("session record cannot be verified") from exc

    def _load(self) -> None:
        """Load sessions from disk."""
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if payload.get("version") != self._VERSION or not isinstance(
                payload.get("sessions"), dict
            ):
                raise ValueError("unsupported session store")
            
            now = time.time()
            records = payload["sessions"]
            for token_digest, sealed in records.items():
                if (
                    not isinstance(token_digest, str)
                    or len(token_digest) != 64
                    or any(c not in "0123456789abcdef" for c in token_digest)
                    or not isinstance(sealed, str)
                ):
                    raise ValueError("invalid session record")
                try:
                    data = self._unprotect(token_digest, sealed)
                    # Check if session is still valid
                    if now - data.get("issued_at", 0) <= self._SESSION_TIMEOUT:
                        self._sessions[token_digest] = data
                except (SessionStoreUnavailable, ValueError, KeyError):
                    # Skip invalid or expired sessions
                    pass
        except Exception:
            # Keep the original file intact
            self._sessions = {}
            self._unavailable = True

    def _write(self) -> None:
        """Write sessions to disk."""
        if self._unavailable:
            raise SessionStoreUnavailable("session store is unavailable")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        try:
            if os.name != "nt":
                self.data_dir.chmod(0o700)
        except OSError:
            pass
        
        # Filter out expired sessions
        now = time.time()
        valid_sessions = {}
        for token_digest, data in self._sessions.items():
            if now - data.get("issued_at", 0) <= self._SESSION_TIMEOUT:
                valid_sessions[token_digest] = data
        
        # Encrypt and prepare for storage
        records = {}
        for token_digest, data in valid_sessions.items():
            records[token_digest] = self._protect(data)
        
        body = json.dumps(
            {"version": self._VERSION, "sessions": records},
            ensure_ascii=True,
            separators=(",", ":"),
        )
        temp = self.data_dir / f"dashboard_sessions.{secrets.token_hex(8)}.tmp"
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
            self._sessions = valid_sessions
        except Exception as exc:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
            if isinstance(exc, SessionStoreUnavailable):
                raise
            raise SessionStoreUnavailable("session store could not be written") from exc

    def save_session(self, token: str, session_key: str, issued_at: float | None = None) -> None:
        """Save a new session."""
        if not isinstance(token, str) or not token:
            raise ValueError("token must be a non-empty string")
        if not isinstance(session_key, str) or not session_key:
            raise ValueError("session_key must be a non-empty string")
        
        token_digest = self._digest(token)
        issued_at = issued_at or time.time()
        
        with self._lock:
            if self._unavailable:
                raise SessionStoreUnavailable("session store is unavailable")
            self._sessions[token_digest] = {
                "token": token,
                "token_digest": token_digest,
                "session_key": session_key,
                "issued_at": issued_at,
            }
            self._write()

    def get_session(self, token: str) -> dict[str, Any] | None:
        """Retrieve a session by token."""
        try:
            token_digest = self._digest(token)
        except ValueError:
            return None
        
        with self._lock:
            if self._unavailable:
                return None
            data = self._sessions.get(token_digest)
            if data is None:
                return None
            # Check if session is still valid
            if time.time() - data.get("issued_at", 0) > self._SESSION_TIMEOUT:
                # Remove expired session
                del self._sessions[token_digest]
                self._write()
                return None
            return data

    def remove_session(self, token: str) -> bool:
        """Remove a session by token."""
        try:
            token_digest = self._digest(token)
        except ValueError:
            return False
        
        with self._lock:
            if self._unavailable:
                raise SessionStoreUnavailable("session store is unavailable")
            if token_digest not in self._sessions:
                return False
            del self._sessions[token_digest]
            self._write()
            return True

    def clear_all(self) -> int:
        """Clear all sessions."""
        with self._lock:
            count = len(self._sessions)
            try:
                self.path.unlink(missing_ok=True)
                for temp in self.data_dir.glob("dashboard_sessions.*.tmp"):
                    temp.unlink(missing_ok=True)
            except OSError as exc:
                raise SessionStoreUnavailable("session store could not be cleared") from exc
            self._sessions = {}
            self._unavailable = False
            return count

    def cleanup_expired(self) -> int:
        """Remove expired sessions and return count of removed."""
        now = time.time()
        removed = 0
        with self._lock:
            to_remove = [
                token_digest for token_digest, data in self._sessions.items()
                if now - data.get("issued_at", 0) > self._SESSION_TIMEOUT
            ]
            for token_digest in to_remove:
                del self._sessions[token_digest]
                removed += 1
            if removed > 0:
                self._write()
        return removed

    def __len__(self) -> int:
        return len(self._sessions)
