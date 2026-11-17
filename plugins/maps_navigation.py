"""Privacy-conscious geocoding and routing with OpenStreetMap services."""
import math
import urllib.parse
import webbrowser

import requests

from core import outcome
from memory.config_manager import get_plugin_config

_HEADERS = {"User-Agent": "JINX-IA/1.0 (desktop maps; contact: project maintainer)",
            "Accept": "application/json"}
_NOMINATIM = "https://nominatim.openstreetmap.org"
_OSRM = "https://router.project-osrm.org/route/v1/driving"

PLUGIN = {
    "name": "maps_navigation",
    "description": (
        "Find routes and nearby places using OpenStreetMap/Nominatim and OSRM, or open a requested address "
        "in Google Street View. For a nearby place use a configured base address or ask the user for a CEP; "
        "never infer the computer's location. Google Maps API is an optional fallback when a key is configured."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["route", "nearest", "street_view", "geocode"]},
        "destination": {"type": "STRING", "description": "Place or destination address"},
        "place": {"type": "STRING", "description": "Kind of nearby place, e.g. pharmacy"},
        "origin": {"type": "STRING", "description": "Optional starting address; otherwise saved base address"},
    }, "required": ["action"]},
}

PLUGIN_SETTINGS = {"namespace": "maps_navigation", "title": "MAPAS E NAVEGAÇÃO / MAPS",
    "fields": [
        {"key": "base_address", "label": "Endereço base ou CEP / Base address or ZIP code", "type": "text",
         "placeholder": "Opcional; não detectamos sua localização automaticamente"},
        {"key": "google_maps_key", "label": "Chave opcional Google Maps / Optional Google Maps key", "type": "password"},
    ]}


def _geocode(address, key=""):
    query = str(address or "").strip()
    if not query or len(query) > 240:
        raise ValueError("Informe um endereço ou CEP válido.")
    if key:
        response = requests.get("https://maps.googleapis.com/maps/api/geocode/json",
            params={"address": query, "key": key}, headers=_HEADERS, timeout=(4, 12), allow_redirects=False)
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") == "OK" and payload.get("results"):
            location = payload["results"][0]["geometry"]["location"]
            return {"lat": float(location["lat"]), "lon": float(location["lng"]),
                    "label": str(payload["results"][0].get("formatted_address", query)), "source": "Google Maps"}
        if payload.get("status") not in {"REQUEST_DENIED", "INVALID_REQUEST", "ZERO_RESULTS"}:
            raise ValueError("Google Maps indisponível: " + str(payload.get("status", "erro")))
    response = requests.get(_NOMINATIM + "/search", params={"q": query, "format": "jsonv2", "limit": 1},
                            headers=_HEADERS, timeout=(4, 15), allow_redirects=False)
    response.raise_for_status()
    rows = response.json()
    if not rows:
        raise ValueError("Endereço não encontrado.")
    row = rows[0]
    return {"lat": float(row["lat"]), "lon": float(row["lon"]),
            "label": str(row.get("display_name", query)), "source": "OpenStreetMap Nominatim"}


def _route(start, finish, key=""):
    if key:
        response = requests.get("https://maps.googleapis.com/maps/api/directions/json",
            params={"origin": f"{start['lat']},{start['lon']}", "destination": f"{finish['lat']},{finish['lon']}",
                    "mode": "driving", "key": key}, headers=_HEADERS, timeout=(4, 15), allow_redirects=False)
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") == "OK" and payload.get("routes"):
            leg = payload["routes"][0]["legs"][0]
            return {"distance_m": int(leg["distance"]["value"]), "duration_s": int(leg["duration"]["value"]),
                    "source": "Google Maps"}
        if payload.get("status") not in {"REQUEST_DENIED", "INVALID_REQUEST", "ZERO_RESULTS"}:
            raise ValueError("Google Directions indisponível: " + str(payload.get("status", "erro")))
    coords = f"{start['lon']},{start['lat']};{finish['lon']},{finish['lat']}"
    response = requests.get(_OSRM + "/" + coords, params={"overview": "false", "alternatives": "false"},
                            headers=_HEADERS, timeout=(4, 20), allow_redirects=False)
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != "Ok" or not payload.get("routes"):
        raise ValueError("A rota não foi encontrada.")
    route = payload["routes"][0]
    return {"distance_m": int(route["distance"]), "duration_s": int(route["duration"]), "source": "OSRM/OpenStreetMap"}


def _nearest(base, place):
    query = str(place or "").strip()
    if not query or len(query) > 120:
        raise ValueError("Informe o tipo de local que procura.")
    params = {"q": query, "format": "jsonv2", "limit": 1, "viewbox":
              f"{base['lon']-0.12},{base['lat']+0.12},{base['lon']+0.12},{base['lat']-0.12}", "bounded": 1}
    response = requests.get(_NOMINATIM + "/search", params=params, headers=_HEADERS,
                            timeout=(4, 15), allow_redirects=False)
    response.raise_for_status()
    rows = response.json()
    if not rows:
        raise ValueError("Não encontrei esse tipo de local perto do endereço base.")
    row = rows[0]
    point = {"lat": float(row["lat"]), "lon": float(row["lon"]),
             "label": str(row.get("display_name", query)), "source": "OpenStreetMap Nominatim"}
    km = _route(base, point)["distance_m"] / 1000
    return point, km


def _open_street_view(address):
    query = str(address or "").strip()
    if not query or len(query) > 240:
        raise ValueError("Informe o endereço do Street View.")
    point = _geocode(query, str(get_plugin_config("maps_navigation").get("google_maps_key") or "").strip())
    url = "https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=" + urllib.parse.quote(
        f"{point['lat']},{point['lon']}")
    accepted = webbrowser.open(url)
    return url, accepted, point


def run(parameters, player=None, session_memory=None):
    p = parameters or {}
    action = p.get("action")
    cfg = get_plugin_config("maps_navigation")
    key = str(cfg.get("google_maps_key") or "").strip()
    try:
        if action == "street_view":
            url, accepted, point = _open_street_view(p.get("destination"))
            return outcome.unverified("maps_navigation", "Street View opened by a browser request; imagery availability is not verified",
                                      address=point["label"], url=url, browser_accepted=accepted)
        if action == "nearest":
            base_address = p.get("origin") or cfg.get("base_address")
            if not base_address:
                return outcome.ask("maps_navigation", "Qual endereço ou CEP devo usar como ponto de partida?",
                                   action="nearest", place=p.get("place"))
            base = _geocode(base_address, key)
            found, distance = _nearest(base, p.get("place"))
            return outcome.done("maps_navigation", place=found["label"], distance_km=round(distance, 2),
                                source=found["source"])
        if action in {"route", "geocode"}:
            destination = p.get("destination")
            if not destination:
                return outcome.failed("maps_navigation", "Informe o destino.")
            target = _geocode(destination, key)
            if action == "geocode":
                return outcome.done("maps_navigation", address=target["label"], latitude=target["lat"],
                                    longitude=target["lon"], source=target["source"])
            origin = p.get("origin") or cfg.get("base_address")
            if not origin:
                return outcome.ask("maps_navigation", "Qual endereço ou CEP devo usar como ponto de partida?",
                                   action="route", destination=destination)
            start = _geocode(origin, key)
            route = _route(start, target, key)
            return outcome.done("maps_navigation", origin=start["label"], destination=target["label"],
                                distance_km=round(route["distance_m"] / 1000, 1),
                                duration_min=math.ceil(route["duration_s"] / 60), source=route["source"])
        return outcome.failed("maps_navigation", "Ação inválida.")
    except (ValueError, requests.RequestException, KeyError, TypeError) as exc:
        return outcome.failed("maps_navigation", str(exc)[:240])
