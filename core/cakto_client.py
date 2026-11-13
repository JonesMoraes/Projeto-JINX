"""Read-only Cakto sales client adapted from jgm-source; see NOTICE.md."""
import hashlib
import math
import re
import threading
import time
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from memory.config_manager import get_plugin_config

BASE = "https://api.cakto.com.br/public_api"
_tokens = {}
_token_lock = threading.Lock()
MAX_PAGES = 10
QUERY_SECONDS = 40


class CaktoError(RuntimeError):
    pass


class NotConfigured(CaktoError):
    pass


def _response(response):
    if not 200 <= response.status_code < 300:
        raise CaktoError(f"Cakto HTTP {response.status_code}")
    try:
        return response.json()
    except Exception:
        raise CaktoError("Resposta inválida / Invalid response") from None


class Client:
    def __init__(self, values=None):
        cfg = get_plugin_config("cakto") if values is None else values
        self.cid = str(cfg.get("client_id") or "").strip()
        self.secret = str(cfg.get("client_secret") or "").strip()
        if not self.cid or not self.secret:
            raise NotConfigured("Configure sua conta em ⚙ → plugins → Cakto / Set your account in plugin settings")
        self.fingerprint = hashlib.sha256((self.cid + "\0" + self.secret).encode()).hexdigest()

    def _bearer(self, invalidate=None):
        import requests
        with _token_lock:
            cached = _tokens.get(self.fingerprint)
            if cached and cached[0] != invalidate and time.monotonic() < cached[1]:
                return cached[0]
            try:
                data = _response(requests.post(BASE + "/token/", data={
                    "client_id": self.cid, "client_secret": self.secret},
                    timeout=(4, 12), allow_redirects=False))
                token = data.get("access_token")
                ttl = float(data["expires_in"])
                if not isinstance(token, str) or not token or not math.isfinite(ttl) or ttl <= 0:
                    raise ValueError("Invalid token response")
                # A short-lived token must never be cached beyond its expiry.
                expires = time.monotonic() + ttl - min(30, ttl / 10)
                if len(_tokens) >= 8:
                    _tokens.clear()
                _tokens[self.fingerprint] = (token, expires)
                return token
            except CaktoError:
                raise
            except Exception:
                raise CaktoError("Falha de autenticação / Authentication failed") from None

    def get(self, path, **params):
        import requests
        if path not in ("/orders/", "/products/") and not re.fullmatch(r"/orders/[A-Za-z0-9-]{1,128}/", path):
            raise CaktoError("Consulta não permitida / Query not allowed")
        try:
            token = self._bearer()
            for attempt in range(2):
                response = requests.get(BASE + path, headers={"Authorization": "Bearer " + token},
                    params=params, timeout=(4, 12), allow_redirects=False)
                if response.status_code == 401 and attempt == 0:
                    token = self._bearer(invalidate=token)
                    continue
                return _response(response)
        except CaktoError:
            raise
        except Exception:
            # Never expose raw exceptions, response bodies, tokens or customer data.
            raise CaktoError("Falha de conexão / Connection failed") from None


def page(data):
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise CaktoError("Formato de página inválido / Invalid page format")
    if any(not isinstance(row, dict) for row in data["results"]):
        raise CaktoError("Pedido inválido / Invalid order")
    count = data.get("count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise CaktoError("Contagem inválida / Invalid count")
    return data["results"], count, bool(data.get("next"))


def amount(order, currency):
    if str(order.get("currency", "")).upper() != currency:
        raise CaktoError("Moeda ausente ou divergente / Currency missing or mismatched")
    try:
        value = Decimal(str(order["amount"]))
        if not value.is_finite() or value < 0:
            raise ValueError("Invalid amount")
        return value
    except (KeyError, InvalidOperation, ValueError):
        raise CaktoError("Valor monetário inválido / Invalid monetary amount") from None


def bounds(action, month=None):
    today = datetime.now().astimezone().date()
    if action == "today_revenue":
        start_date, end_date = today, today + timedelta(days=1)
    else:
        ym = str(month or today.strftime("%Y-%m"))
        if not re.fullmatch(r"\d{4}-\d{2}", ym):
            raise ValueError("month")
        year, number = map(int, ym.split("-"))
        start_date = datetime(year, number, 1).date()
        end_date = datetime(year + (number == 12), 1 if number == 12 else number + 1, 1).date()
    return (datetime.combine(start_date, datetime.min.time()).astimezone(),
            datetime.combine(end_date, datetime.min.time()).astimezone())


def revenue(client, start, end, currency):
    total, paid, skipped, seen = Decimal("0"), 0, 0, set()
    expected = None
    complete = False
    deadline = time.monotonic() + QUERY_SECONDS
    pages = 0
    for number in range(1, MAX_PAGES + 1):
        if time.monotonic() >= deadline:
            break
        rows, count, has_more = page(client.get("/orders/", page=number, limit=100,
            currency=currency, status="paid", ordering="-paidAt",
            paidAt__gte=start.isoformat(), paidAt__lt=end.isoformat()))
        pages += 1
        if expected is None:
            expected = count
        elif expected != count:
            break  # Data moved during pagination: never claim an exact total.
        duplicate = False
        for order in rows:
            oid = order.get("id")
            if not oid or str(oid) in seen:
                duplicate = True
                continue
            seen.add(str(oid))
            if order.get("status") != "paid" or any(order.get(k) for k in (
                    "refundedAt", "chargedbackAt", "canceledAt")):
                skipped += 1
                continue
            try:
                timestamp = datetime.fromisoformat(str(order.get("paidAt")).replace("Z", "+00:00"))
                if timestamp.tzinfo is None or not start <= timestamp < end:
                    raise ValueError("date outside query")
                value = amount(order, currency)
            except (ValueError, CaktoError):
                skipped += 1
                continue
            total += value
            paid += 1
        if duplicate or not rows and has_more:
            break
        if not has_more:
            complete = len(seen) == expected and skipped == 0
            break
    return {"gross_paid": str(total), "currency": currency, "paid_orders": paid,
            "complete": complete, "pages": pages, "skipped": skipped,
            "period_start": start.isoformat(), "period_end_exclusive": end.isoformat()}
