"""Rate-limited, read-only OpenSky and OpenStreetMap data fetch."""
from __future__ import annotations
import json
import math
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_lock = threading.Lock()
_last_request = 0.0
MIN_INTERVAL = 120.0


def fetch(lat: float, lon: float, radius_km: int = 25):
    global _last_request
    lat, lon, radius_km = float(lat), float(lon), int(radius_km)
    if not -90 <= lat <= 90 or not -180 <= lon <= 180 or not 10 <= radius_km <= 100:
        raise ValueError("Coordinates or radar radius outside allowed limits")
    with _lock:
        now = time.monotonic()
        if now - _last_request < MIN_INTERVAL:
            raise RuntimeError("Radar refresh is limited to one request every two minutes")
        _last_request = now
    dlat = radius_km / 110.57; dlon = min(90, radius_km / (111.32 * max(.1, math.cos(math.radians(lat)))))
    box = (max(-90, lat-dlat), max(-180, lon-dlon), min(90, lat+dlat), min(180, lon+dlon))
    result = {"center": {"lat": lat, "lon": lon}, "radius_km": radius_km,
              "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "planes": [], "airports": [], "sources": [], "errors": []}
    query = urlencode({"lamin": box[0], "lomin": box[1], "lamax": box[2], "lomax": box[3]})
    try:
        req = Request("https://opensky-network.org/api/states/all?" + query,
                      headers={"User-Agent": "JINX-IA/1.0 read-only local radar"})
        with urlopen(req, timeout=8) as response:
            data = json.loads(response.read(2_000_000).decode("utf-8"))
        for row in (data.get("states") or [])[:400]:
            if len(row) < 11 or row[5] is None or row[6] is None: continue
            result["planes"].append({"lat": row[6], "lon": row[5], "callsign": str(row[1] or "").strip(),
                                     "altitude_m": row[7], "speed_mps": row[9], "heading": row[10]})
        result["sources"].append("OpenSky")
    except Exception as exc: result["errors"].append("OpenSky: " + type(exc).__name__)
    try:
        bbox = f"{box[0]},{box[1]},{box[2]},{box[3]}"
        ql = f'[out:json][timeout:8];(nwr["aeroway"~"^(aerodrome|heliport)$"]({bbox}););out center tags 30;'
        body = urlencode({"data": ql}).encode()
        req = Request("https://overpass-api.de/api/interpreter", data=body,
                      headers={"User-Agent": "JINX-IA/1.0 read-only local radar",
                               "Content-Type": "application/x-www-form-urlencoded"})
        with urlopen(req, timeout=10) as response:
            data = json.loads(response.read(1_000_000).decode("utf-8"))
        for item in (data.get("elements") or [])[:30]:
            center = item.get("center") or item
            if "lat" in center and "lon" in center:
                result["airports"].append({"lat": center["lat"], "lon": center["lon"],
                                           "name": (item.get("tags") or {}).get("name", "Aerodrome")})
        result["sources"].append("OpenStreetMap/Overpass")
    except Exception as exc: result["errors"].append("Overpass: " + type(exc).__name__)
    if not result["sources"]: raise RuntimeError("Radar sources unavailable: " + ", ".join(result["errors"]))
    return result
