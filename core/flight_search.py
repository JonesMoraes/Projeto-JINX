"""Route/date flight research using existing multi-mode web search; no bookings."""
import re
from datetime import date, datetime, timedelta
from urllib.parse import urlencode
from core import gemini, outcome


def normalize_date(raw):
    raw = str(raw or "").strip()
    relative = {"today": 0, "hoje": 0, "tomorrow": 1, "amanhã": 1, "amanha": 1}
    if raw.casefold() in relative:
        return (date.today() + timedelta(days=relative[raw.casefold()])).isoformat()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try: return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError: pass
    if not raw or re.fullmatch(r"[\d/-]+", raw): raise ValueError("Data inválida / Invalid date")
    parsed = gemini.text("Today is " + date.today().isoformat() + ". Convert the date expression to YYYY-MM-DD only; if ambiguous return UNKNOWN. " +
        outcome.untrusted("flight-date", raw), tier=gemini.FAST, timeout_ms=10000)
    return date.fromisoformat(parsed.strip()).isoformat()  # Never silently substitute today.


def booking_url(origin, destination, departure, returning=None, passengers=1, cabin="economy"):
    query = f"Flights from {origin} to {destination} on {departure}"
    if returning: query += " returning " + returning
    query += f" {passengers} passengers {cabin}"
    return "https://www.google.com/travel/flights?" + urlencode({"q": query, "curr": "BRL"})


def run(parameters, player=None):
    try:
        p = parameters or {}
        origin, destination = str(p.get("origin", "")).strip(), str(p.get("destination", "")).strip()
        if not origin or not destination or len(origin) > 80 or len(destination) > 80 or origin.casefold() == destination.casefold():
            raise ValueError("Informe origem/destino diferentes / Provide distinct origin/destination")
        departure = normalize_date(p.get("date"))
        returning = normalize_date(p["return_date"]) if p.get("return_date") else None
        count = p.get("passengers", 1)
        cabin = p.get("cabin", "economy")
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 9 or cabin not in ("economy", "premium", "business", "first"):
            raise ValueError("Passageiros 1–9 e classe válida / Passengers 1–9 and valid cabin required")
        if date.fromisoformat(departure) < date.today() or (returning and returning < departure):
            raise ValueError("Data passada/retorno anterior à ida / Past date/return precedes departure")
        mode = p.get("mode", "price")
        if mode not in ("search", "price", "research"): raise ValueError("search mode")
        link = booking_url(origin, destination, departure, returning, count, cabin)
        from actions.web_search import web_search
        query = f"Flights {origin} to {destination}, departure {departure}" + (f", return {returning}" if returning else "") + f", {count} passengers, {cabin}, prices BRL"
        results = web_search({"query": query, "mode": mode})
        caution = ("Pesquisa web de voos; preços, assentos e horários precisam de confirmação na companhia. O link é busca, não reserva/cotação verificada.\n"
                   "Flight web research; verify prices, seats and schedules with airline. Link is search, not booking/verified quote.\n")
        report = caution + f"{origin} → {destination} | {departure}" + (f" → {returning}" if returning else "") + "\n" + link + "\n\n" + results
        path = ""
        if p.get("save") is True:
            from core.office import created
            from pathlib import Path
            path = created(report.encode("utf-8"), ".txt", "Voos-Flights", Path.home() / "Desktop")
        if player: player.show_content("Pesquisa de voos / Flight search", report[:3900])
        # Research may be retrieved, but no fare or availability is independently verified.
        return outcome.unverified("flight_search", caution, data=outcome.untrusted("flight-web-results", report), saved_path=path)
    except Exception as exc:
        return outcome.failed("flight_search", str(exc)[:250])
