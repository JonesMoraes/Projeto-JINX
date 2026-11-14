"""Read-only local area air radar; coordinates are supplied per request."""
import threading
from core import radar, outcome

PLUGIN = {"name": "local_radar", "description": "Open a read-only local radar with aircraft from OpenSky and airports from OpenStreetMap. Ask for map coordinates and radius; do not infer or save location. Data may be delayed or unavailable.",
    "parameters": {"type": "OBJECT", "properties": {"latitude": {"type": "NUMBER"},
        "longitude": {"type": "NUMBER"}, "radius_km": {"type": "INTEGER"}},
        "required": ["latitude", "longitude"]}}


def run(parameters, player=None, session_memory=None):
    try:
        if player is None or not callable(getattr(player, "show_radar", None)):
            return outcome.failed("local_radar", "Desktop HUD visualization unavailable")
        lat = float(parameters.get("latitude")); lon = float(parameters.get("longitude"))
        radius = int(parameters.get("radius_km", 25))
        if not -90 <= lat <= 90 or not -180 <= lon <= 180 or not 10 <= radius <= 100:
            return outcome.failed("local_radar", "Check the coordinates and choose a radius from 10 to 100 km")
        def work():
            try:
                data = radar.fetch(lat, lon, radius)
                player.show_radar(data)
            except Exception as exc:
                player.show_content("Radar indisponível", f"{type(exc).__name__}: {str(exc)[:220]}")
        threading.Thread(target=work, daemon=True, name="jinx-local-radar").start()
        return outcome.unverified("local_radar", "Fetching public radar sources; results will appear in the HUD", center=f"{lat:.3f},{lon:.3f}")
    except Exception as exc:
        return outcome.failed("local_radar", str(exc)[:220])
