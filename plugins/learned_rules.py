"""Persistent behaviour rules: propose, review, list and change, always with a person's approval.

The assistant can propose a rule ("create rule: ...") and can list or change stored
rules. A proposal is stored only after the user presses CONFIRM on the HUD. Any
change to a stored rule (enable, disable, edit, remove) is shown and confirmed
on the HUD first. Model parameters can never accept a rule or skip a confirmation.
"""
import json

from core import learned_rules as rules, outcome

PLUGIN = {
    "name": "learned_rules",
    "description": (
        "Regras de comportamento / Behaviour rules. Use for: 'remember to always ...', "
        "'always ask ... before ...', 'never ... without confirmation' (action propose, text = the rule "
        "in one imperative sentence; the user then confirms on the HUD). 'list rules' (action list). "
        "'enable rule X', 'disable rule X', 'edit rule X', 'remove rule X' (action enable, disable, edit, "
        "remove with id = the rule id; the user confirms on the HUD). 'review' and 'reject' work on a "
        "pending proposal id. Rules are style or workflow preferences only. They never change safety, "
        "tool permissions or confirmations."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["propose", "list", "pending", "review", "reject",
                                              "enable", "disable", "edit", "remove"]},
        "text": {"type": "STRING"},
        "id": {"type": "STRING"},
        "kind": {"type": "STRING", "enum": ["style", "workflow"]},
        "priority": {"type": "INTEGER"},
    }, "required": ["action"]},
}

_CHANGE = ("enable", "disable", "edit", "remove")


def run(parameters, player=None, session_memory=None):
    try:
        p = dict(parameters)
        action = p.get("action")
        if action == "propose":
            row = rules.propose(p.get("text"), p.get("kind", "style"),
                                source="voice", priority=p.get("priority"))
            if player:
                player.show_content("Preferência proposta / Proposed preference",
                                    row["id"] + "\n" + row["text"])
            return outcome.done("rule_proposal", id=row["id"],
                                note="Pending review on the HUD; not stored")
        if action in ("list", "pending"):
            rows = rules.list_rules() if action == "list" else rules.pending()
            text = json.dumps(rows, ensure_ascii=False)
            if player:
                player.show_content("Preferências / Preferences", text)
            return outcome.done("learned_rules", data=outcome.untrusted("preferences", text))
        if action == "review":
            return rules.review(p.get("id"), player)
        if action == "reject":
            return rules.reject(p.get("id"))
        if action in _CHANGE:
            return rules.review_change(action, p.get("id"), player,
                                       text=p.get("text"), priority=p.get("priority"))
        raise ValueError("action")
    except ValueError as exc:
        # Validation messages are written for the user, so they are passed on as they are.
        return outcome.failed("learned_rules", str(exc))
    except Exception:
        return outcome.failed("learned_rules",
                              "Não foi possível aplicar; confira ação, ID ou arquivo / "
                              "Could not apply; check action, ID or store")
