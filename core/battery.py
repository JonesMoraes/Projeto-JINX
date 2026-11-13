"""Read-only battery telemetry and opt-in threshold alerts; no new dependencies."""
import base64
import json
import math
import os
import platform
import subprocess
import threading
import time

import psutil
from core import outcome, undo
from memory.config_manager import get_plugin_config, save_plugin_config, get_plugin_enabled

DEFAULTS = {"enabled": False, "low": "20", "high": "80"}
_lock = threading.RLock()
# Fixed query, never accepts model/user text. Match packs by InstanceName.
_QUERY = r"""
$ErrorActionPreference='Stop'
$static=@(Get-CimInstance -Namespace root/wmi -ClassName BatteryStaticData)
$full=@(Get-CimInstance -Namespace root/wmi -ClassName BatteryFullChargedCapacity)
@($static | ForEach-Object {
  $s=$_; $f=@($full | Where-Object {$_.InstanceName -eq $s.InstanceName})
  if ($f.Count -eq 1) {
    [pscustomobject]@{design=$s.DesignedCapacity; full=$f[0].FullChargedCapacity}
  }
}) | ConvertTo-Json -Compress
"""


def settings():
    cfg = {**DEFAULTS, **get_plugin_config("battery")}
    low, high = int(cfg["low"]), int(cfg["high"])
    if not 5 <= low < high <= 100:
        raise ValueError("Limites: 5 <= mínimo < máximo <= 100 / Thresholds: 5 <= low < high <= 100")
    return {"enabled": cfg["enabled"] is True, "low": low, "high": high}


def configure(values):
    with _lock:
        before = {**DEFAULTS, **get_plugin_config("battery")}
        desired = {**before, **values}
        low, high = int(desired["low"]), int(desired["high"])
        if not 5 <= low < high <= 100 or not isinstance(desired["enabled"], bool):
            raise ValueError("thresholds/enabled")
        saved = {"enabled": desired["enabled"], "low": str(low), "high": str(high)}
        save_plugin_config("battery", saved)
        if any(get_plugin_config("battery").get(k) != v for k, v in saved.items()):
            raise RuntimeError("Battery settings not verified")

        def restore():
            with _lock:
                if any(get_plugin_config("battery").get(k) != v for k, v in saved.items()):
                    return outcome.failed("battery_undo", "Configuração mudou / Settings changed")
                old = {k: before[k] for k in saved}
                save_plugin_config("battery", old)
                if any(get_plugin_config("battery").get(k) != v for k, v in old.items()):
                    return outcome.failed("battery_undo", "Gravação não confirmada / Write not verified")
            return outcome.done("battery_undo")
        undo.push_undo("Alertas de bateria / Battery alerts", restore)
        return settings()


def snapshot():
    value = psutil.sensors_battery()
    if value is None:
        return None
    percent = float(value.percent)
    if not math.isfinite(percent) or not 0 <= percent <= 100:
        raise ValueError("Invalid battery percentage")
    plugged = value.power_plugged if isinstance(value.power_plugged, bool) else None
    seconds = value.secsleft
    remaining = (round(seconds / 60) if plugged is False and isinstance(seconds, (float, int))
                 and math.isfinite(seconds) and seconds >= 0 else None)
    return {"percent": percent, "power_connected": plugged,
            "state": "discharging" if plugged is False else "power_connected_charging_unknown" if plugged else "unknown",
            "remaining_minutes_estimate": remaining}


def health():
    if platform.system() != "Windows":
        return {"status": "unverified", "reason": "Saúde não disponibilizada nesta plataforma / Health unavailable on this platform"}
    try:
        command = base64.b64encode(_QUERY.encode("utf-16le")).decode("ascii")
        executable = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                                  "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
        result = subprocess.run([executable, "-NoProfile", "-NonInteractive", "-EncodedCommand", command],
                                capture_output=True, text=True, timeout=4,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=True)
        rows = json.loads(result.stdout)
        rows = [rows] if isinstance(rows, dict) else rows
        if not isinstance(rows, list) or not rows:
            raise ValueError("No battery capacities")
        packs = []
        for row in rows:
            design, full = float(row["design"]), float(row["full"])
            if not all(math.isfinite(v) and 0 < v < 0xffffffff for v in (design, full)):
                continue
            ratio = full / design * 100
            packs.append({"pack": len(packs) + 1, "capacity_percent_estimate": round(ratio, 1),
                          "wear_percent_estimate": round(max(0, 100 - ratio), 1)})
        if not packs:
            raise ValueError("Invalid capacities")
        return {"status": "done", "source": "Windows WMI battery driver", "packs": packs,
                "note": "Estimativa de capacidade, não diagnóstico; depende do firmware / Capacity estimate, not diagnosis; firmware-dependent"}
    except Exception:
        return {"status": "unverified", "reason": "Windows/driver não forneceu capacidades válidas / Windows/driver did not provide valid capacities"}


class BatteryAlerts:
    """Latch per charge/discharge episode. Quiet/busy periods never consume alerts."""
    def __init__(self):
        self.signature = None
        self.sent = set()
        self.last = float("-inf")

    def pending(self, reading, cfg, allowed=True, now=None):
        signature = (cfg["enabled"], cfg["low"], cfg["high"])
        if signature != self.signature:
            self.signature, self.sent = signature, set()
        if not cfg["enabled"] or not get_plugin_enabled("battery_health") or reading is None:
            return None
        percent, plugged = reading["percent"], reading["power_connected"]
        if percent > cfg["low"] + 3 or plugged is True:
            self.sent.discard("low")
        if percent < cfg["high"] - 3 or plugged is False:
            self.sent.discard("high")
        key = ("low" if plugged is False and percent <= cfg["low"] else
               "high" if plugged is True and percent >= cfg["high"] else None)
        now = time.monotonic() if now is None else now
        return key if key and key not in self.sent and allowed and now - self.last >= 300 else None

    def delivered(self, key, now=None):
        self.sent.add(key)
        self.last = time.monotonic() if now is None else now


async def poll(host, alerts):
    """One monitor tick, shared by Live and the configured pipeline session."""
    from datetime import datetime
    cfg = settings()
    if not cfg["enabled"] or not get_plugin_enabled("battery_health"):
        return
    allowed = bool(host.session and host._awake and not host.ui.muted and not host._is_speaking
                   and time.monotonic() - host._last_user_speech >= 10)
    if host._routines is not None:
        allowed = allowed and not host._routines.in_quiet(datetime.now())
    reading = snapshot()
    key = alerts.pending(reading, cfg, allowed)
    if key:
        text = (f"[BATTERY ALERT] Battery {reading['percent']}%; external power connected: "
                f"{reading['power_connected']}; configured {key} threshold reached. "
                "Briefly inform the user in their current language. Do not call tools or change power settings.")
        await host.session.send_client_content(turns={"role": "user", "parts": [{"text": text}]}, turn_complete=True)
        alerts.delivered(key)
