"""core/autonomy.py — the single execution policy every tool call goes through.

WHY THIS EXISTS
    JINX could already do a lot bit by bit, but the decision "may this run?"
    was scattered across individual actions (and often nowhere at all). This
    module concentrates that decision in ONE function, evaluate(), so autonomy
    has a shape:

    - A DENY floor that no level can cross: credential stores, other users'
      profiles, system write paths, and destructive shell patterns. A refusal
      here is final; the answer is "do it by hand".
    - A DESTRUCTIVE ACL: irreversible actions (power, deletion, killing
      processes, external messages, changes to JINX itself). These always
      surface to a HUMAN through the HUD confirm banner — the model is never
      in the confirmation loop — or, at level 3, queue for an explicit later
      command within a per-day budget (default 0).
    - Everything else runs at once and relies on core/undo.py, exactly as the
      codebase already philosophises: undo is faster than a question.

    It also keeps trust counters (for reporting), a pause switch that drops
    destructive capability for 24h whenever the user undoes an autonomous
    action, and the hooks episodic memory needs to record what actually ran.

WHAT BELONGS HERE
    Policy only. Handlers keep ownership of validating their exact targets.
"""
from __future__ import annotations

import fnmatch
import json
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from memory.config_manager import get_plugin_config, save_plugin_config

_log = threading.RLock()

NAMESPACE = "autonomy"
QUEUE_PATH = Path(__file__).resolve().parents[1] / "config" / "autonomy_queue.json"
QUEUE_MAX = 50

LEVELS = {0: "pausado", 1: "assistente", 2: "confiável", 3: "autônomo"}
DEFAULT_LEVEL = 3            # full autonomy from the first run, owner request
DEFAULT_BUDGET = 3           # destructive rows/Day spent from the queue; the
                             # queue itself still needs an explicit "run N"
PAUSE_HOURS_AFTER_UNDO = 24

# ── Tool families ─────────────────────────────────────────────────────────────
# Heuristic floor, not a ceiling. A decorator/deeper mapping can be added later;
# until then name sets + keyword scans decide.
FS_TOOLS = {"file_controller", "fs_total", "desktop", "edit_block",
            "file_processor", "media_convert", "pdf_forge", "docs_native"}
SHELL_TOOLS = {"shell_persistent", "repl_polyglot", "ssh_ops"}
MESSAGING_TOOLS = {"send_message"}
POWER_TOOLS = {"computer_settings"}
KILL_TOOLS = {"process_manager"}
UPDATE_TOOLS = {"update_jinx", "game_updater"}

_DELETE_WORDS = re.compile(r"\b(delet\w*|remov\w*|exclu\w*|apag\w*|erase|unlink|rmdir|del /|rd /|\brm -\w*r)", re.I)
_POWER_WORDS = re.compile(r"\b(shutdown|deslig\w*|reinici\w*|restart|reboot|logoff|sign.?out|encerrar sess\w*)", re.I)
_KILL_WORDS = re.compile(r"\b(kill|taskkill|encerrar|finalizar)\b", re.I)

# Shell commands that must never come from the model. Manual execution only.
_SHELL_DENY = re.compile(
    r"(?i)\b(format\b|diskpart|cipher\s+/w|reg\s+(delete|add)|sc\s+delete|"
    r"delete\s+shadows|vssadmin|bcdedit|shutdown|restart.?computer|"
    r"remove-item[^|\n]*-recurse[^|\n]*-force|del\s+/f\s+/s|rd\s+/s|"
    r"taskkill\s+/f|wmic\s+process\s+delete|schtasks\s+/(create|change))", re.I)
# Credential-shaped file targets: reads protected at every level.
_CREDENTIAL_NAMES = re.compile(
    r"(?i)(login.?data|web.?data|cookies(\.sqlite)?|key4?\.db|logins\.json|"
    r"key(helpers|chain)?|wallet\.dat|\.kdbx|\.pem|id_rsa|id_ed25519|"
    r"\.env$|credentials?\.json|ntuser\.dat|ntds\.dit|\bsam\b)")
_SYSTEM_DIRS = ("windows", "program files", "program files (x86)", "programdata")

_MAX_TRUST = 100  # counters are reporting data; keep the store bounded


# ── Config plumbing ───────────────────────────────────────────────────────────

def _cfg() -> dict:
    cfg = get_plugin_config(NAMESPACE)
    out = {"level": DEFAULT_LEVEL, "paused_until": "", "budget": DEFAULT_BUDGET,
           "trust": {}, "extra_deny": []}
    if isinstance(cfg, dict):
        for key, default in out.items():
            value = cfg.get(key)
            if key == "trust":
                out[key] = value if isinstance(value, dict) else {}
            elif key == "extra_deny":
                out[key] = [str(v)[:200] for v in value][:100] if isinstance(value, list) else []
            elif key in ("level", "budget"):
                try:
                    out[key] = max(0, min(3, int(value))) if key == "level" else max(0, int(value))
                except (TypeError, ValueError):
                    pass
            else:
                out[key] = str(value or "")
    return out


def _save(cfg: dict) -> None:
    save_plugin_config(NAMESPACE, {"level": cfg["level"], "budget": cfg["budget"],
                                   "trust": cfg["trust"], "paused_until": cfg["paused_until"],
                                   "extra_deny": cfg["extra_deny"]})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _paused(cfg: dict) -> bool:
    text = str(cfg.get("paused_until") or "")
    if not text:
        return False
    try:
        return datetime.fromisoformat(text) > _now()
    except ValueError:
        return False


def level() -> int:
    cfg = _cfg()
    return 0 if _paused(cfg) else int(cfg["level"])


def level_name() -> str:
    return LEVELS.get(level(), "?")


def set_level(value: int) -> int:
    value = max(0, min(3, int(value)))
    cfg = _cfg()
    cfg["level"] = value
    if value > 0:
        cfg["paused_until"] = ""
    _save(cfg)
    return value


def pause(hours: float = 0.0) -> str:
    until = (_now() + (timedelta(hours=max(0.5, hours)) if hours > 0
                       else timedelta(hours=PAUSE_HOURS_AFTER_UNDO)))
    cfg = _cfg()
    cfg["paused_until"] = until.isoformat()
    _save(cfg)
    return f"Autonomia pausada até {until.astimezone().strftime('%d/%m %H:%M')}"


def resume() -> str:
    cfg = _cfg()
    cfg["paused_until"] = ""
    _save(cfg)
    return "Autonomia retomada."


def note_undo() -> None:
    """An undo means an autonomous decision was wrong: fall back for 24h."""
    try:
        pause()
    except Exception:
        pass


def set_budget(value: int) -> int:
    cfg = _cfg()
    cfg["budget"] = max(0, min(20, int(value)))
    _save(cfg)
    return cfg["budget"]


def _count(cfg: dict, name: str, key: str, cap: int = 999) -> None:
    trust = cfg.setdefault("trust", {})
    row = trust.get(name) or {}
    row[key] = min(cap, int(row.get(key, 0)) + 1)
    trust[name] = row
    if len(trust) > _MAX_TRUST:
        oldest = sorted(trust.items(), key=lambda kv: str(kv[1]))[:32]
        for k, _ in oldest:
            trust.pop(k, None)


# ── Deny floor ────────────────────────────────────────────────────────────────

def _as_path(value: str) -> Path | None:
    text = str(value or "").strip().strip('"')
    if not text or "\n" in text or len(text) > 500:
        return None
    if re.fullmatch(r"[A-Za-z]:\\?.*", text) or text.startswith(("/", "~")) or "\\\\" in text:
        try:
            return Path(text[:500]).expanduser()
        except (OSError, ValueError):
            return None
    return None


def _under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _extra_deny_hit(path: Path, cfg: dict) -> bool:
    for pattern in cfg.get("extra_deny", []):
        try:
            if fnmatch.fnmatch(str(path).lower(), str(pattern).lower()):
                return True
        except Exception:
            continue
    return False


def fs_violation(params: dict, cfg: dict) -> str:
    """Return a refusal reason when a path-like parameter hits the deny floor."""
    user_home = Path.home()
    users_root = user_home.parent

    def _values(node: Any, depth: int = 0):
        if depth > 6:
            return
        if isinstance(node, dict):
            for v in node.values():
                yield from _values(v, depth + 1)
        elif isinstance(node, (list, tuple)):
            for v in node:
                yield from _values(v, depth + 1)
        else:
            yield node

    for value in _values(params):
        path = _as_path(str(value))
        if path is None:
            continue
        lowered = str(path).lower()
        if _CREDENTIAL_NAMES.search(Path(lowered).name or lowered):
            return "caminho de credencial/sessão protegido"
        if _extra_deny_hit(path, cfg):
            return (f"caminho na lista de negação do usuário "
                    f"({pattern_peek(cfg, path)})")
        if _under(path, users_root) and not _under(path, user_home):
            return "caminho dentro do perfil de outro usuário"
        if Path(lowered).anchor:
            norm = lowered.replace("\\", "/").strip("/")
            norm = re.sub(r"^[a-z]:/", "", norm)
            if any(norm.startswith(d + "/") for d in _SYSTEM_DIRS):
                return "caminho do sistema protegido"
    return ""


def pattern_peek(cfg: dict, path: Path) -> str:
    for pattern in cfg.get("extra_deny", []):
        if fnmatch.fnmatch(str(path).lower(), str(pattern).lower()):
            return str(pattern)
    return "??"


def shell_violation(params: dict) -> str:
    for value in params.values():
        if isinstance(value, str) and len(value) > 2500:
            continue
        if not isinstance(value, str):
            continue
        if _SHELL_DENY.search(value):
            return "comando na lista de negação do shell"
    return ""


# ── Classification ────────────────────────────────────────────────────────────

def classify(name: str, parameters: dict) -> str:
    """Action kind for the destructive ACL. '' means not on the ACL."""
    blob = json.dumps(parameters, ensure_ascii=False, default=str)[:4000]
    if name in POWER_TOOLS and _POWER_WORDS.search(blob):
        return "power"
    if name in KILL_TOOLS and _KILL_WORDS.search(blob):
        return "kill"
    if name in MESSAGING_TOOLS:
        return "messaging"
    if name in UPDATE_TOOLS:
        return "self_update"
    if name in FS_TOOLS and _DELETE_WORDS.search(blob):
        return "fs_delete"
    if name in SHELL_TOOLS:
        _hit = shell_violation(parameters)
        if _hit:
            return "shell_denied"
    return ""


# ── Queue (level 3 destructive overflow) ─────────────────────────────────────

def _read_queue() -> list[dict]:
    try:
        rows = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
        return rows if isinstance(rows, list) else []
    except Exception:
        return []


def _write_queue(rows: list[dict]) -> None:
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = QUEUE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(QUEUE_PATH)


def queue_add(name: str, parameters: dict, reason: str) -> int:
    with _log:
        rows = _read_queue()
        rows = rows[-(QUEUE_MAX - 1):]
        rows.append({"id": f"{int(time.time())}-{len(rows)}", "name": str(name)[:120],
                     "parameters": parameters, "reason": str(reason)[:200],
                     "day": _now().date().isoformat(), "status": "pending"})
        _write_queue(rows)
        return len(rows)


def queue_run(index: int, runner: Callable[[], str]) -> str:
    """Execute one queued destructive action. Only ever called from the
    autonomy_control tool, which the user must have explicitly requested."""
    with _log:
        rows = _read_queue()
        pending = [r for r in rows if r.get("status") == "pending"]
        if not 1 <= index <= len(pending):
            return "Item da fila não encontrado."
        cfg = _cfg()
        today = _now().date().isoformat()
        spent = sum(1 for r in rows if r.get("status") == "ran" and r.get("day") == today)
        if spent >= int(cfg.get("budget", 0)):
            return (f"Orçamento diário de ações destrutivas esgotado "
                    f"({spent}/{cfg.get('budget', 0)}). Peça-me para elevá-lo ou execute manualmente.")
        row = pending[index - 1]  # same dict object as in rows: mutating marks it
        row["status"] = "ran"
        _write_queue(rows)
    return (runner() or "Done.") + f" [fila #{index}]"


def queue_list() -> list[dict]:
    return [r for r in _read_queue() if r.get("status") == "pending"]


# ── The gate ──────────────────────────────────────────────────────────────────

def evaluate(name: str, parameters: dict) -> dict:
    """Policy decision for a tool call: {"mode": run|confirm|queue|block, ...}.

    mode=block    — deny floor; the call never runs at any level.
    mode=confirm  — irreversible; surfaced to the human via the HUD banner.
    mode=queue    — level 3 with budget left; parked for an explicit command.
    mode=run      — everything else: execute now, rely on undo + audit.
    """
    cfg = _cfg()
    if name in FS_TOOLS:
        violation = fs_violation(parameters, cfg)
        if violation:
            return {"mode": "block", "reason": violation}
    if name in SHELL_TOOLS:
        violation = shell_violation(parameters)
        if violation:
            return {"mode": "block", "reason": violation}

    kind = classify(name, parameters)
    if not kind:
        return {"mode": "run", "reason": "não-destrutivo"}

    if _paused(cfg) or cfg["level"] == 0:
        return {"mode": "block", "reason": "autonomia pausada; execute manualmente"}
    if cfg["level"] >= 3 and int(cfg.get("budget", 0)) > 0:
        # The queue lives HERE, in the policy, and nowhere else: enqueueing is a
        # consequence of the decision, and re-dispatching a row from the queue
        # goes through run_direct() below the gate, so this cannot loop.
        slot = queue_add(name, parameters, kind)
        return {"mode": "queue", "reason": kind, "slot": slot}
    return {"mode": "confirm", "reason": kind}


def run_direct(registry: Callable[[str, dict, dict | None], str],
               name: str, parameters: dict, ctx: dict | None = None) -> str:
    """Execute one already-queued destructive action past the queue branch of
    the gate. Only ever called by autonomy_control's queue runner, which the
    user must have explicitly requested. Deny-floor violations are re-checked:
    a parked row can never smuggle in what the floor refuses."""
    cfg = _cfg()
    if name in FS_TOOLS:
        violation = fs_violation(parameters, cfg)
        if violation:
            return f"Recusado na fila ({violation})."
    if name in SHELL_TOOLS:
        violation = shell_violation(parameters)
        if violation:
            return f"Recusado na fila ({violation})."
    return registry(name, parameters, ctx)


def note_decision(name: str, mode: str, kind: str) -> None:
    """Persist a counter for the settings report. Never raises."""
    try:
        cfg = _cfg()
        _count(cfg, name, {"confirm": "confirms", "block": "blocks",
                           "queue": "queued"}.get(mode, "runs"))
        _save(cfg)
    except Exception:
        pass
