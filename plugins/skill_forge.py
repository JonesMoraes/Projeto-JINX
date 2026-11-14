"""Foreground-only skill draft for human review; output stays inert Markdown."""
import threading
from core import skill_forge

PLUGIN = {
    "name": "skill_forge",
    "description": "Create a reusable instruction-skill draft for a clearly described goal and show it for review. This tool never writes, registers, executes, or grants it to background agents.",
    "parameters": {"type": "OBJECT", "properties": {
        "goal": {"type": "STRING", "description": "Goal and intended user workflow for the proposed skill"}},
        "required": ["goal"]}}


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        goal = skill_forge.validate_goal(parameters.get("goal", ""))
        if player is None or not callable(getattr(player, "show_content", None)):
            return "Open the JINX HUD to review the generated draft."
        def work():
            try:
                text = skill_forge.draft(goal)
                player.show_content("Skill draft — review only", text)
            except Exception as exc:
                player.show_content("Skill draft failed", f"{type(exc).__name__}: {str(exc)[:240]}")
        threading.Thread(target=work, daemon=True, name="skill-forge-draft").start()
        return "I am drafting the skill for review in the HUD. It will not be installed or run."
    except Exception as exc:
        return f"Could not start the skill draft: {type(exc).__name__}."
