"""Per-instance Windows WMI brightness, verified readback and guarded undo."""
import base64
import json
import platform
import os
import subprocess
from types import SimpleNamespace
from contextlib import contextmanager
from core import outcome, undo


@contextmanager
def connection():
    if platform.system() != "Windows":
        raise RuntimeError("Windows WMI unavailable")
    class Session:
        def query(self, script):
            exe = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
            encoded = base64.b64encode(("$ErrorActionPreference='Stop';" + script).encode("utf-16le")).decode("ascii")
            r = subprocess.run([exe, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                capture_output=True, text=True, timeout=5, check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0, shell=False))
            return json.loads(r.stdout or "null")
        def WmiMonitorBrightness(self):
            rows = self.query("@(Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightness | Select-Object InstanceName,Active,CurrentBrightness) | ConvertTo-Json -Compress")
            return [SimpleNamespace(**r) for r in ([rows] if isinstance(rows, dict) else rows or [])]
        def WmiMonitorBrightnessMethods(self):
            def method(name):
                def write(Brightness, Timeout):
                    encoded = base64.b64encode(name.encode("utf-8")).decode("ascii")
                    return self.query("$id=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + encoded + "')); "
                        "Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightnessMethods | Where-Object {$_.InstanceName -eq $id} | "
                        "Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{Brightness=[byte]" + str(int(Brightness)) + ";Timeout=[uint32]1} | ConvertTo-Json -Compress")
                return write
            return [SimpleNamespace(InstanceName=r.InstanceName, WmiSetBrightness=method(r.InstanceName)) for r in self.WmiMonitorBrightness()]
    yield Session()


def monitors(client):
    return {str(r.InstanceName): int(r.CurrentBrightness)
            for r in client.WmiMonitorBrightness() if r.Active}


def set_one(client, name, value):
    matches = [r for r in client.WmiMonitorBrightnessMethods() if str(r.InstanceName) == name]
    if len(matches) != 1:
        raise ValueError("Monitor disconnected or ambiguous")
    matches[0].WmiSetBrightness(Brightness=value, Timeout=1)
    return monitors(client).get(name) == value


def run(parameters, player=None, **context):
    try:
        p = parameters or {}
        action = p.get("action", "list")
        if action not in ("list", "set"):
            raise ValueError("action")
        with connection() as client:
            rows = monitors(client)
            if not rows:
                return outcome.unverified("monitor_brightness", "WMI não expõe monitores; use o controle físico/global existente / WMI exposes no monitors; use physical/existing global control")
            if action == "list":
                return outcome.done("monitor_brightness", data=outcome.untrusted("monitors", json.dumps(rows)),
                    note="Somente monitores expostos pelo WMI; externos DDC podem não aparecer / Only WMI-exposed monitors; external DDC displays may be absent")
            name, value = p.get("monitor"), p.get("percent")
            if name is None and len(rows) == 1:
                name = next(iter(rows))
            if name not in rows or isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
                raise ValueError("Select exact monitor from list; percent 0–100")
            before = rows[name]
            if not set_one(client, name, value):
                return outcome.unverified("monitor_brightness", "Brilho solicitado, leitura não confirmou / Brightness requested, readback did not confirm")

        def restore():
            with connection() as c:
                if monitors(c).get(name) != value:
                    return outcome.failed("brightness_undo", "Monitor/brilho mudou / Monitor/brightness changed")
                return (outcome.done("brightness_undo") if set_one(c, name, before) else
                        outcome.unverified("brightness_undo", "Leitura não confirmou / Readback did not confirm"))
        undo.push_undo("Brilho do monitor / Monitor brightness", restore)
        return outcome.done("monitor_brightness", percent=value)
    except ValueError:
        return outcome.failed("monitor_brightness", "Liste e selecione o monitor exato; percentual 0–100 / List and select exact monitor; percentage 0–100")
    except Exception:
        return outcome.unverified("monitor_brightness", "Controle WMI indisponível; brilho global legado continua disponível / WMI control unavailable; legacy global control remains available")


TOOL = {"name": "monitor_brightness", "description": "List WMI monitors and set brightness on an exact monitor; readback and undo. Unsupported external displays reported honestly.",
    "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING", "enum": ["list", "set"]},
    "monitor": {"type": "STRING"}, "percent": {"type": "INTEGER"}}, "required": ["action"]},
    "handler": run, "tier": "extra", "brief": "Per-monitor brightness list/set with readback and undo."}
