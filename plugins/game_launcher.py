import json
from core import games, outcome

PLUGIN = {"name": "game_launcher", "description": "List installed Steam/Epic/Riot games from local metadata or launch an exact listed name/ID. No install/update/purchase. Launch success requires observing a process in the game folder.",
    "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING", "enum": ["list", "launch"]},
    "name": {"type": "STRING"}, "store": {"type": "STRING", "enum": ["steam", "epic", "riot"]}}, "required": ["action"]}}


def run(parameters, player=None, session_memory=None):
    try:
        p = parameters or {}
        rows = games.discover()
        if p.get("store"):
            rows = [r for r in rows if r["store"] == p["store"]]
        if p.get("action", "list") == "list":
            return outcome.done("game_list", data=outcome.untrusted("game-names", json.dumps([
                {k: r[k] for k in ("store", "id", "name")} for r in rows])),
                note="Lista apenas instalações detectáveis; vazia não prova ausência / Detectable installations only; empty does not prove none installed")
        if p.get("action") != "launch":
            raise ValueError("action")
        name = str(p.get("name", "")).casefold()
        matches = [r for r in rows if name in (r["name"].casefold(), r["id"].casefold())]
        if len(matches) != 1:
            return outcome.failed("game_launch", "Nome ausente/ambíguo; liste e escolha loja/ID / Name missing/ambiguous; list and choose store/ID")
        return games.launch(matches[0])
    except Exception:
        return outcome.failed("game_launcher", "Detecção/inicialização não verificada / Discovery/launch not verified")
