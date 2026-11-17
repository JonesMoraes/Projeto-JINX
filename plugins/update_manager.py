"""Opt-in release checks and verified staged updates."""
from core import updater, outcome


def _install(_values):
    updater.set_enabled(True)
    return True, "Opt-in enabled. Updates are checked only when you ask."


PLUGIN = {"name": "update_manager",
    "description": "Manage opt-in updates. Actions: status, enable, disable, check a stable GitHub release, stage its SHA-256 verified ZIP, or apply a staged version. No background polling or unattended install.",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["status", "enable", "disable", "check", "stage", "apply"]},
        "stage_directory": {"type": "STRING"}}, "required": ["action"]}}
PLUGIN_SETTINGS = {"namespace": "updater", "title": "ATUALIZAÇÕES / UPDATES", "fields": [],
                   "action": {"label": "ATIVAR ATUALIZAÇÕES SOB DEMANDA / ENABLE OPT-IN UPDATES", "run": _install}}


def run(parameters, player=None, session_memory=None):
    p = parameters or {}; action = p.get("action")
    try:
        if action == "status": return outcome.done("updater", enabled=updater.enabled())
        if action == "enable": updater.set_enabled(True); return "Updates enabled; checks happen only when requested."
        if action == "disable": updater.set_enabled(False); return "Updates disabled."
        if action == "check":
            release = updater.check_latest()
            return outcome.unverified("updater_release", "Stable release metadata and asset digest found; no files downloaded", tag=release["tag"], name=release["name"], page=release["page"])
        if action == "stage":
            result = updater.stage()
            if player: player.show_content("Atualização preparada", str(result))
            return outcome.unverified("updater_stage", "Release asset was hash-checked and staged; no files replaced", **result)
        if action == "apply":
            if player is None or not callable(getattr(player, "request_close", None)):
                return outcome.failed("updater", "Open the desktop HUD to restart and apply the staged update")
            from core import confirm as confirmation
            if confirmation.pending_title(): return outcome.failed("updater", "Another confirmation is pending")
            folder = p.get("stage_directory", "")
            # Validate the staged path before applying an update.
            candidate = __import__("pathlib").Path(folder).resolve(strict=True)
            if updater.STATE.resolve() not in candidate.parents or not (candidate / "update-manifest.json").is_file():
                return outcome.failed("updater", "Choose a valid staged release")
            player.show_content("Aplicar atualização", f"Versão preparada: {candidate.name}\nO JINX será fechado, arquivos de código serão verificados e substituídos com cópia para rollback; depois reabre.")
            return confirmation.request("apply_update", "Apply staged JINX update?",
                "Close JINX, replace verified project code, and reopen. User data folders are excluded.",
                lambda: updater.apply_after_restart(str(candidate), player))
        return outcome.failed("updater", "Unknown update action")
    except Exception as exc:
        return outcome.failed("updater", f"Update unavailable: {type(exc).__name__}: {str(exc)[:180]}")
