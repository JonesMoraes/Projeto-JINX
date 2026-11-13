"""Bounded opt-in price/uptime/RAM checks; separate from legacy news topics."""
import copy
import math
import re
import threading
import time
import uuid
from urllib.parse import urlsplit
import psutil
import requests
from core import outcome, undo
from memory.config_manager import get_plugin_config, save_plugin_config, get_plugin_enabled

_lock = threading.RLock()


def entries():
    rows = get_plugin_config("system_watchers").get("entries", [])
    if not isinstance(rows, list) or len(rows) > 10:
        raise ValueError("Invalid watcher store")
    return copy.deepcopy(rows)


def change(action, p):
    with _lock:
        before = entries()
        rows = copy.deepcopy(before)
        if action == "remove":
            rows = [r for r in rows if r["id"] != p.get("id")]
            if len(rows) == len(before):
                raise ValueError("ID not found")
        else:
            if len(rows) >= 10:
                raise ValueError("Limit: 10")
            kind = p.get("kind")
            threshold = float(p.get("threshold", 90))
            interval = int(p.get("interval", 300))
            if kind not in ("crypto", "website", "ram") or not 60 <= interval <= 86400 or not math.isfinite(threshold):
                raise ValueError("Invalid watcher")
            row = {"id": uuid.uuid4().hex[:12], "kind": kind, "interval": interval,
                   "threshold": threshold, "direction": p.get("direction", "above")}
            if row["direction"] not in ("above", "below"):
                raise ValueError("direction")
            if kind == "crypto":
                row.update(coin=str(p.get("coin", "")).lower(), currency=str(p.get("currency", "brl")).lower())
                if not re.fullmatch(r"[a-z0-9-]{1,80}", row["coin"]) or row["currency"] not in ("brl", "usd", "eur") or threshold <= 0:
                    raise ValueError("CoinGecko ID and positive price required")
            elif kind == "website":
                from core.tasks.web import check_url
                row["url"] = str(p.get("url", ""))
                u = urlsplit(row["url"])
                if u.scheme != "https" or u.username or u.password:
                    raise ValueError("Public HTTPS URL required")
                check_url(row["url"])
            elif not 1 <= threshold <= 100:
                raise ValueError("RAM 1–100")
            rows.append(row)
        save_plugin_config("system_watchers", {"entries": rows})
        if entries() != rows:
            raise RuntimeError("Write unverified")
        def restore():
            with _lock:
                if entries() != rows:
                    return outcome.failed("watchers_undo", "Lista mudou / List changed")
                save_plugin_config("system_watchers", {"entries": before})
                return (outcome.done("watchers_undo") if entries() == before else
                        outcome.failed("watchers_undo", "Gravação não confirmada / Write not verified"))
        undo.push_undo("Monitoramento / Watchers", restore)
        return rows


def sample(row):
    if row["kind"] == "ram":
        return float(psutil.virtual_memory().percent)
    if row["kind"] == "website":
        from core.tasks.web import check_url
        check_url(row["url"])
        try:
            with requests.head(row["url"], timeout=5, allow_redirects=False) as response:
                return 200 <= response.status_code < 400
        except requests.RequestException:
            return False
    with requests.get("https://api.coingecko.com/api/v3/simple/price", params={
            "ids": row["coin"], "vs_currencies": row["currency"]}, timeout=5) as response:
        response.raise_for_status()
        value = float(response.json()[row["coin"]][row["currency"]])
        if not math.isfinite(value) or value < 0:
            raise ValueError("Invalid quote")
        return value


class Monitor:
    def __init__(self):
        self.state = {}

    def check(self, rows, allowed=True, now=None):
        now = time.monotonic() if now is None else now
        live = {r["id"] for r in rows}
        self.state = {k: v for k, v in self.state.items() if k in live}
        alerts = []
        for row in rows:
            state = self.state.setdefault(row["id"], {"next": 0, "sent": False})
            if now >= state["next"]:
                state["next"] = now + row["interval"]
                try:
                    value = sample(row)
                    active = (not value if row["kind"] == "website" else
                              value >= row["threshold"] if row["direction"] == "above" else value <= row["threshold"])
                    previous = state.get("value")
                    state.update(value=value, active=active, error=False)
                    if row["kind"] == "website" and previous is not None and previous != value:
                        state.update(sent=False, recovered=bool(value))
                    if not active:
                        state["sent"] = False
                        if row["kind"] == "website" and previous is False:
                            state["recovered"] = True
                except Exception:
                    state["error"] = True
                    continue  # A quote error is not a price or threshold crossing.
            if allowed and not state.get("error") and not state["sent"] and (state.get("active") or state.get("recovered")):
                alerts.append((row["id"], {"watcher": row, "observed": state["value"], "recovered": state.get("recovered", False)}))
        return alerts

    def delivered(self, key):
        self.state[key].update(sent=True, recovered=False)


async def poll(host, monitor):
    import asyncio
    import json
    from datetime import datetime
    cfg = get_plugin_config("system_watchers")
    if cfg.get("enabled") is not True or not get_plugin_enabled("system_watchers"):
        return
    allowed = bool(host.session and host._awake and not host.ui.muted and not host._is_speaking
                   and time.monotonic() - host._last_user_speech >= 10)
    if host._routines is not None:
        allowed = allowed and not host._routines.in_quiet(datetime.now())
    pending = await asyncio.to_thread(monitor.check, entries(), allowed)
    for key, data in pending:
        await host.session.send_client_content(turns={"role": "user", "parts": [{"text":
            "[WATCHER ALERT] Briefly report the observed data in the user's language; no trading advice or tools.\n" +
            outcome.untrusted("watcher-data", json.dumps(data))}]}, turn_complete=True)
        monitor.delivered(key)
