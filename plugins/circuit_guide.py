"""DHT11 and Pro Mini wiring guide; generation never writes to hardware."""
import json
from core import circuit_guide, outcome

PLUGIN = {"name": "circuit_guide",
    "description": "Create a DHT11 with Arduino Pro Mini wiring plan and example code after confirming the exact board variant, 3.3V/5V, and bare sensor/module. Never flashes hardware.",
    "parameters": {"type": "OBJECT", "properties": {
        "board_voltage": {"type": "STRING", "enum": ["3.3V", "5V"]},
        "sensor_form": {"type": "STRING", "enum": ["module", "bare"]},
        "board_variant": {"type": "STRING", "enum": ["Pro Mini 3.3V/8MHz", "Pro Mini 5V/16MHz"]}},
        "required": ["board_voltage", "sensor_form", "board_variant"]}}


def run(parameters, player=None, session_memory=None):
    try:
        data = circuit_guide.guide((parameters or {}).get("board_voltage"),
                                   (parameters or {}).get("sensor_form"),
                                   (parameters or {}).get("board_variant"))
        if player: player.show_content("DHT11 + Pro Mini", json.dumps(data, ensure_ascii=False, indent=2))
        return outcome.done("circuit_guide", data=json.dumps(data, ensure_ascii=False), note=data["warning"])
    except Exception as exc:
        return outcome.failed("circuit_guide", str(exc)[:220])
