"""Trello primitives adapted from jgm-source (see NOTICE.md).

Only the official API is used. Credentials always come from the user's config.
"""
from urllib.parse import quote
import hashlib
from memory.config_manager import get_plugin_config

API = "https://api.trello.com/1"


class TrelloError(RuntimeError):
    pass


def account_fingerprint():
    cfg = get_plugin_config("trello")
    return hashlib.sha256((str(cfg.get("api_key")) + "|" + str(cfg.get("token"))).encode()).hexdigest()


def ident(value):
    value = str(value or "")
    if not value.isalnum():
        raise TrelloError("ID Trello inválido / Invalid Trello ID")
    return quote(value, safe="")


def request(method, path, values=None, credentials=None):
    import requests
    cfg = credentials if credentials is not None else get_plugin_config("trello")
    auth = {k: str(cfg.get(k) or "").strip() for k in ("api_key", "token")}
    if not all(auth.values()):
        raise TrelloError("Configure sua chave e token em ⚙ → plugins → Trello / Set your key and token")
    if not path.startswith("/") or ".." in path or "?" in path:
        raise TrelloError("Invalid API path")
    params = {**(values or {}), "key": auth["api_key"], "token": auth["token"]}
    params = {k: str(v).lower() if isinstance(v, bool) else v for k, v in params.items()}
    try:
        response = requests.request(method, API + path, params=params, timeout=(4, 12),
                                    allow_redirects=False)
        if response.status_code >= 300:
            raise TrelloError(f"Trello HTTP {response.status_code}")
        return response.json()
    except TrelloError:
        raise
    except Exception:
        # Requests exceptions can contain the URL and auth query parameters.
        raise TrelloError("Falha de conexão ou resposta / Connection or response failure") from None


def pick(items, name):
    query = str(name or "").strip().casefold()
    for test in (lambda n: n == query, lambda n: n.startswith(query)):
        hits = [x for x in items if query and test(str(x.get("name", "")).casefold())]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            break
    raise TrelloError("Nome ausente ou ambíguo / Missing or ambiguous name")


def boards():
    return request("GET", "/members/me/boards", {"filter": "open", "fields": "name,url"})


def lists(board):
    return request("GET", f"/boards/{ident(board)}/lists", {"filter": "open", "fields": "name"})


def cards(list_id):
    result = request("GET", f"/lists/{ident(list_id)}/cards", {
        "fields": "name,due,dueComplete,closed,idList,dateLastActivity,desc"})
    if not isinstance(result, list):
        raise TrelloError("Invalid cards response")
    return result


def card(card_id):
    return request("GET", f"/cards/{ident(card_id)}", {
        "fields": "name,due,dueComplete,closed,idList,dateLastActivity,desc"})


def update(card_id, changes):
    path = f"/cards/{ident(card_id)}"
    request("PUT", path, changes)
    actual = card(card_id)
    for k, v in changes.items():
        expected, observed = v, actual.get(k)
        if k == "due" and v and observed:
            from datetime import datetime
            expected = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            observed = datetime.fromisoformat(str(observed).replace("Z", "+00:00"))
        if k != "pos" and observed != expected:
            raise TrelloError("Alteração sem confirmação / Change not verified")
    return actual
