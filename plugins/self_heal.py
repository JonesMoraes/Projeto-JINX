"""Human-reviewed source repair. Disabled by default."""
import threading
from core import self_heal

PLUGIN = {
    "name": "self_heal",
    "description": "Check self-repair status, enable or disable it, generate a syntax-checked repair proposal for a project Python file, list proposals, or request human review. Repairs are OFF by default and are never applied without the HUD confirmation.",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["status", "enable", "disable", "propose", "list", "review"]},
        "path": {"type": "STRING", "description": "Project-relative Python file path for propose"},
        "diagnostic": {"type": "STRING", "description": "Error report for a candidate repair"},
        "candidate_id": {"type": "STRING"}}, "required": ["action"]}}


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        action = parameters.get("action")
        if action == "status":
            return f"Self-repair is {'ON' if self_heal.enabled() else 'OFF'}. Protected files: boot, UI, security and loaders."
        if action == "enable":
            self_heal.set_enabled(True)
            return "Self-repair enabled. It only proposes changes; the HUD must confirm each repair."
        if action == "disable":
            self_heal.set_enabled(False)
            return "Self-repair disabled."
        if action == "propose":
            if player is None or not callable(getattr(player, "show_content", None)):
                return "Open the JINX HUD to review a repair candidate."
            path = str(parameters.get("path", ""))
            diagnostic = str(parameters.get("diagnostic", ""))
            def work():
                try:
                    row = self_heal.propose(path, diagnostic)
                    player.show_content("Repair proposal — review only", str(row))
                except Exception as exc:
                    player.show_content("Repair proposal failed", f"{type(exc).__name__}: {str(exc)[:200]}")
            threading.Thread(target=work, daemon=True, name="self-heal-proposal").start()
            return "Checking the file and preparing a syntax-checked candidate. No source file will change until you review and confirm it."
        if action == "list":
            return str(self_heal.list_pending() or "No repair proposals pending.")
        if action == "review":
            return self_heal.review(parameters.get("candidate_id", ""), player)
        return "Unknown self-repair action."
    except Exception as exc:
        return f"Self-repair could not complete: {type(exc).__name__}."
