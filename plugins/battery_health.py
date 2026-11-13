"""Original read-only battery feature and reversible alert preferences."""
import json
from core import battery, outcome

PLUGIN = {"name": "battery_health", "description": "Battery charge, external power, remaining-time estimate and Windows capacity/wear where reported. Configure optional voice alerts (low/high percent) or disable; no power changes.",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["status", "alerts", "disable"]},
        "low": {"type": "INTEGER", "description": "Low alert 5–99; must be below high"},
        "high": {"type": "INTEGER", "description": "High alert up to 100; must exceed low"}}, "required": ["action"]}}

PLUGIN_SETTINGS = {"namespace": "battery", "title": "BATERIA / BATTERY", "fields": [
    {"key": "enabled", "label": "Alertas de carga / Charge alerts", "type": "toggle", "default": False},
    {"key": "low", "label": "Mínimo % (5–99) / Low %", "type": "text", "default": "20"},
    {"key": "high", "label": "Máximo % (até 100) / High %", "type": "text", "default": "80"}]}


def run(parameters, player=None, session_memory=None):
    try:
        p = parameters or {}
        action = p.get("action", "status")
        if action in ("alerts", "disable"):
            values = {"enabled": action == "alerts"}
            for key in ("low", "high"):
                if key in p:
                    if isinstance(p[key], bool) or not isinstance(p[key], int):
                        raise ValueError("integer thresholds required")
                    values[key] = str(p[key])
            cfg = battery.configure(values)
            return outcome.done("battery_alerts", settings=json.dumps(cfg),
                note="Alertas só com sessão ativa, respeitando silêncio; sem bateria não há alertas / Alerts require active session, respect quiet hours; no battery means no alerts")
        if action != "status":
            raise ValueError("action")
        reading = battery.snapshot()
        if reading is None:
            return outcome.unverified("battery_health", "Sistema não detectou bateria / No battery detected by OS")
        reading["health"] = battery.health()
        return outcome.done("battery_status", data=json.dumps(reading, ensure_ascii=False),
            note="Tomada não comprova carregamento; saúde indisponível é unverified / AC connection does not prove charging; unavailable health is unverified")
    except (ValueError, TypeError):
        return outcome.failed("battery_health", "Dados/limites inválidos: 5 <= mínimo < máximo <= 100 / Invalid data/thresholds: 5 <= low < high <= 100")
    except Exception:
        return outcome.failed("battery_health", "Leitura/configuração não confirmada / Reading/settings not verified")
