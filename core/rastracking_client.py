"""Rastracking read contract adapted from jgm-source; see NOTICE.md.

Base URL is intentionally unset: the user must supply their own service.
"""
import time
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit
from memory.config_manager import get_plugin_config

MAX_PAGES = 10


class TrackingError(RuntimeError):
    pass


def money(value):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result < 0:
            raise ValueError()
        return result
    except (InvalidOperation, ValueError):
        raise TrackingError("Valor inválido; total não confirmado / Invalid amount; total unverified") from None


def period(name, start=None, end=None):
    today = datetime.now().astimezone().date()
    if name == "custom":
        a, b = date.fromisoformat(str(start)), date.fromisoformat(str(end))
        if a > b:
            raise ValueError("reversed dates")
    elif name == "today":
        a = b = today
    elif name == "yesterday":
        a = b = today - timedelta(days=1)
    elif name == "week":
        a = today - timedelta(days=today.weekday())
        b = a + timedelta(days=6)
    elif name == "month":
        a = today.replace(day=1)
        b = (a.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    else:
        raise ValueError("period")
    return a.isoformat(), b.isoformat()


class Client:
    def __init__(self, values=None):
        cfg = get_plugin_config("rastracking") if values is None else values
        self.base = str(cfg.get("base_url") or "").strip().rstrip("/")
        self.key = str(cfg.get("api_key") or "").strip()
        if not self.base or not self.key:
            raise TrackingError("Informe SEU servidor HTTPS e SUA chave em ⚙ → plugins → Rastracking / Set YOUR HTTPS server and API key")
        url = urlsplit(self.base)
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise TrackingError("Servidor deve ser uma URL HTTPS sem credenciais / Server must be an HTTPS URL without credentials")

    def get(self, path, **params):
        import requests
        if path not in ("clients", "sales", "support/conversations"):
            raise TrackingError("Consulta não permitida / Query not allowed")
        try:
            response = requests.get(self.base + "/" + path, params=params,
                headers={"Authorization": "Bearer " + self.key, "Accept": "application/json"},
                timeout=(4, 12), allow_redirects=False)
            if response.status_code != 200:
                raise TrackingError(f"Rastracking HTTP {response.status_code}")
            data = response.json()
            if not isinstance(data, dict) or not isinstance(data.get("data"), list):
                raise TrackingError("Contrato de resposta divergente / Response contract mismatch")
            if any(not isinstance(row, dict) for row in data["data"]):
                raise TrackingError("Item inválido / Invalid item")
            if not isinstance(data.get("hasMore"), bool):
                raise TrackingError("Paginação não confirmada / Pagination unverified")
            return data
        except TrackingError:
            raise
        except Exception:
            raise TrackingError("Falha de conexão/resposta / Connection or response failure") from None

    def collect(self, path, **params):
        rows, ids, cursors = [], set(), set()
        cursor = None
        deadline = time.monotonic() + 40
        for _ in range(MAX_PAGES):
            if time.monotonic() >= deadline:
                return rows, False
            data = self.get(path, limit=100, **params, **({"cursor": cursor} if cursor else {}))
            for row in data["data"]:
                oid = row.get("id")
                if oid is None or str(oid) in ids:
                    return rows, False
                ids.add(str(oid))
                rows.append(row)
            if not data["hasMore"]:
                return rows, True
            cursor = data.get("nextCursor")
            if not isinstance(cursor, str) or not cursor or cursor in cursors:
                return rows, False
            cursors.add(cursor)
        return rows, False
