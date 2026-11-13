"""Port adapted from João Gabriel, CC BY-NC 4.0; see NOTICE.md."""
import json
from core import outcome, undo
from core import trello_client as api
from memory.config_manager import get_plugin_config

PLUGIN = {
    "name": "trello_control", "description": "Trello boards/lists/cards: read, create, move, complete, archive.",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["boards", "lists", "cards", "create", "move", "complete", "archive"]},
        **{k: {"type": "STRING"} for k in ("board", "list", "card", "to_list", "text")}},
        "required": ["action"]},
}


def _test(values):
    try:
        me = api.request("GET", "/members/me", {"fields": "id"}, credentials=values)
        return bool(me.get("id")), "Sua conta conectada / Your account connected"
    except api.TrelloError as exc:
        return False, str(exc)


PLUGIN_SETTINGS = {"namespace": "trello", "title": "TRELLO — SUA CONTA / YOUR ACCOUNT",
    "fields": [{"key": k, "label": label, "type": typ} for k, label, typ in (
        ("api_key", "Sua chave API / Your API key", "password"),
        ("token", "Seu token / Your token", "password"),
        ("default_board", "Seu quadro padrão / Your default board", "text"))],
    "action": {"label": "TESTAR CONEXÃO / TEST CONNECTION", "run": _test}}


def _change(card_id, changes):
    owner = api.account_fingerprint()
    before = api.card(card_id)
    result = api.update(card_id, changes)
    reverse = {key: before.get(key) for key in changes}
    def restore():
        if api.account_fingerprint() != owner:
            return outcome.failed("trello_undo", "Conta alterada / Account changed")
        current = api.card(card_id)
        if any(current.get(k) != v for k, v in changes.items()):
            return outcome.failed("trello_undo", "Cartão mudou desde a ação / Card changed since action")
        api.update(card_id, reverse)
        return outcome.done("trello_undo")
    undo.push_undo("Trello", restore)
    return result


def run(parameters, player=None, session_memory=None):
    p = parameters or {}
    action = p.get("action")
    try:
        if action == "boards":
            result = api.boards()
        else:
            board = api.pick(api.boards(), p.get("board") or get_plugin_config("trello").get("default_board"))
            columns = api.lists(board["id"])
            if action == "lists":
                result = columns
            else:
                column = api.pick(columns, p.get("list"))
                if action == "cards":
                    result = api.cards(column["id"])
                elif action == "create":
                    name = str(p.get("card") or "").strip()
                    if not name:
                        return outcome.failed("trello", "Informe o título / Provide a title")
                    created = api.request("POST", "/cards", {"idList": column["id"], "name": name,
                        "desc": str(p.get("text") or "")})
                    result = api.card(created["id"])
                    if result.get("name") != name or result.get("idList") != column["id"]:
                        return outcome.unverified("trello", "Cartão criado sem confirmação / Creation not verified")
                    cid = result["id"]
                    owner = api.account_fingerprint()
                    def archive_created():
                        if api.account_fingerprint() != owner:
                            return outcome.failed("trello_undo", "Conta alterada / Account changed")
                        current = api.card(cid)
                        if any(current.get(k) != result.get(k) for k in ("name", "due", "idList", "desc")):
                            return outcome.failed("trello_undo", "Cartão mudou / Card changed")
                        api.update(cid, {"closed": True})
                        return outcome.done("trello_undo")
                    undo.push_undo("Criar cartão / Create card", archive_created)
                elif action in ("move", "complete", "archive"):
                    item = api.pick(api.cards(column["id"]), p.get("card"))
                    changes = ({"idList": api.pick(columns, p.get("to_list"))["id"]} if action == "move"
                               else {"dueComplete": True} if action == "complete" else {"closed": True})
                    result = _change(item["id"], changes)
                else:
                    return outcome.failed("trello", "Ação desconhecida / Unknown action")
        return outcome.done("trello", data=outcome.untrusted("trello", json.dumps(result, ensure_ascii=False)))
    except api.TrelloError as exc:
        return outcome.unverified("trello", str(exc))
    except Exception:
        return outcome.failed("trello", "Falha de integração / Integration failure")
