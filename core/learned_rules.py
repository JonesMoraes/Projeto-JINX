"""Persistent behaviour rules the user has reviewed, kept apart from factual memory.

A rule is an instruction about HOW the assistant responds (style, workflow). It
can never change safety rules, tool permissions, confirmations or undo, and
nothing is stored without a person approving it on the HUD or in the settings
panel. The model can propose a rule; it cannot accept one.

Store: config/learned_rules.json, schema version 2:
    {"version": 2, "rules": [{"id", "text", "kind", "scope", "priority",
                              "enabled", "created_at", "updated_at", "source"}]}
A version 1 file (a bare list of {id, text, kind}) is read and upgraded in
memory. It is written back as version 2 only after the user approves a change.
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from core import confirm, outcome, undo
from memory import config_manager as config

log = logging.getLogger(__name__)

SCHEMA_VERSION = 2
MAX_RULES = 100
MAX_INJECTED = 20
MAX_TEXT = 500
MAX_STORE_BYTES = 256_000
MAX_PENDING = 32
DEFAULT_PRIORITY = 100
PRIORITY_MIN, PRIORITY_MAX = 0, 1000
KINDS = ("style", "workflow")
SCOPES = ("global",)
CHANGE_ACTIONS = ("edit", "enable", "disable", "remove")
_ACTION_TITLE = {"edit": "Editar", "enable": "Ativar", "disable": "Desativar", "remove": "Remover"}

# A rule that asks to switch off safety, confirmation or undo is refused.
# Rules that ask FOR confirmation ("never run X without confirmation") are fine.
_OVERRIDE = re.compile(
    r"ignor\w*\s+(?:todas?|qualquer|as|suas|the|all|any|previous|prior|your|safety|rules|instructions"
    r"|regras|instru[cç][õo]es)"
    r"|desconsider\w*|sobrescrev\w*|\boverride\b|\bbypass\w*|contorn\w*"
    r"|(?:never|nunca)\s+(?:me\s+)?(?:ask|pe[cç]a|pergunte)\w*\s+(?:for\s+)?(?:confirm\w*|confirma\w*)"
    r"|(?:skip|pule|pular|dispens\w*|omit\w*|desativ\w*|disable|desligu\w*)\s+"
    r"(?:the\s+|a\s+|as\s+|o\s+|os\s+|todas?\s+as\s+)?(?:confirma\w*|safety|seguran\w*|desfaz\w*|undo)",
    re.IGNORECASE,
)
# Secrets never belong in a rule, even a reviewed one.
_SECRET = re.compile(
    r"sk-[A-Za-z0-9]{8,}|AIza[0-9A-Za-z_\-]{8,}|api[\s_\-]?key|senha|password|passwd|\btoken\b|\bsecret\b",
    re.IGNORECASE,
)
_ID_RE = re.compile(r"[A-Za-z0-9_\-]{1,64}")

_lock = threading.RLock()
_pending: dict[str, dict] = {}


# ── Validation ───────────────────────────────────────────────────────────────

def _path() -> Path:
    return config.CONFIG_DIR / "learned_rules.json"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean_text(value, *, screen: bool = True) -> str:
    """One line of text, 1 to MAX_TEXT characters. `screen` also refuses secrets
    and rules that would switch off safety; stored rows are re-read unscreened
    so an old, valid file is never locked out by a later stricter rule."""
    if not isinstance(value, str):
        raise ValueError("O texto da regra precisa ser texto.")
    text = " ".join(value.split())
    if not 1 <= len(text) <= MAX_TEXT:
        raise ValueError(f"A regra precisa ter de 1 a {MAX_TEXT} caracteres.")
    if screen and _SECRET.search(text):
        raise ValueError("Regras não podem conter senhas, chaves ou tokens.")
    if screen and _OVERRIDE.search(text):
        raise ValueError("Esta regra tentaria desligar segurança, confirmações ou desfazer; não foi salva.")
    return text


def _clean_priority(value) -> int:
    if isinstance(value, bool):
        raise ValueError("A prioridade precisa ser um número inteiro.")
    try:
        priority = int(value)
    except (TypeError, ValueError):
        raise ValueError("A prioridade precisa ser um número inteiro.") from None
    if not PRIORITY_MIN <= priority <= PRIORITY_MAX:
        raise ValueError(f"A prioridade vai de {PRIORITY_MIN} a {PRIORITY_MAX}.")
    return priority


def _clean_kind(value) -> str:
    if value not in KINDS:
        raise ValueError("O tipo precisa ser style ou workflow.")
    return value


def _check_row(row) -> dict:
    """Return a normalised rule, or raise ValueError. Unknown keys are dropped."""
    if not isinstance(row, dict):
        raise ValueError("Regra inválida no arquivo.")
    rid = row.get("id")
    if not isinstance(rid, str) or not _ID_RE.fullmatch(rid):
        raise ValueError("Regra com identificador inválido.")
    scope = row.get("scope", "global")
    if scope not in SCOPES:
        raise ValueError("Escopo de regra desconhecido.")
    enabled = row.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("Campo 'enabled' inválido.")
    created = row.get("created_at")
    updated = row.get("updated_at", created)
    if not isinstance(created, str) or not isinstance(updated, str):
        raise ValueError("Datas de regra inválidas.")
    source = row.get("source", "legacy")
    if not isinstance(source, str) or len(source) > 32:
        raise ValueError("Origem de regra inválida.")
    return {
        "id": rid,
        "text": _clean_text(row.get("text"), screen=False),
        "kind": _clean_kind(row.get("kind", "style")),
        "scope": scope,
        "priority": _clean_priority(row.get("priority", DEFAULT_PRIORITY)),
        "enabled": enabled,
        "created_at": created,
        "updated_at": updated,
        "source": source,
    }


def _migrate(data, file_time: str) -> list[dict]:
    """Validated rows from a parsed store. Version 1 is upgraded here, in memory."""
    if isinstance(data, list):
        raw = []
        for row in data:
            if isinstance(row, dict):
                row = {**row, "created_at": file_time, "updated_at": file_time, "source": "legacy"}
            raw.append(row)
    elif isinstance(data, dict):
        if data.get("version") != SCHEMA_VERSION:
            raise ValueError("Versão do arquivo de regras não reconhecida; preservado para reparo.")
        raw = data.get("rules")
        if not isinstance(raw, list):
            raise ValueError("Arquivo de regras inválido; preservado para reparo.")
    else:
        raise ValueError("Arquivo de regras inválido; preservado para reparo.")
    if len(raw) > MAX_RULES:
        raise ValueError("Limite de regras excedido; preservado para reparo.")
    rows = [_check_row(row) for row in raw]
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Identificadores duplicados; preservado para reparo.")
    return rows


# ── Storage ──────────────────────────────────────────────────────────────────

def _load(path: Path | None = None) -> list[dict]:
    """All stored rules. Raises ValueError for a file that must be repaired by
    hand, and OSError for one that cannot be read right now. Callers never
    overwrite a file they could not parse."""
    path = path or _path()
    if not path.exists():
        return []
    if path.stat().st_size > MAX_STORE_BYTES:
        raise ValueError("Arquivo de regras grande demais; preservado para reparo.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("Arquivo de regras ilegível; preservado para reparo.") from None
    return _migrate(data, _stamp(path.stat().st_mtime))


def _write_json(path: Path, data: dict) -> None:
    """Write through a temporary file and an atomic replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False,
                                         encoding="utf-8", suffix=".tmp") as handle:
            tmp_name = handle.name
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        for attempt in range(20):
            try:
                os.replace(tmp_name, path)
                break
            except PermissionError:
                # Windows: a scanner or reader may hold the file for a moment.
                if attempt == 19:
                    raise
                time.sleep(0.05)
    finally:
        if tmp_name and os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _save(rows: list[dict]) -> None:
    """Persist all rules, then read them back to prove the write landed."""
    _write_json(_path(), {"version": SCHEMA_VERSION, "rules": rows})
    if _load() != rows:
        raise OSError("A releitura das regras não confere; nada foi confirmado.")


def _next_id(rows: list[dict]) -> str:
    prefix = "rule_" + datetime.now(timezone.utc).strftime("%Y%m%d") + "_"
    used = [int(r["id"][len(prefix):]) for r in rows
            if r["id"].startswith(prefix) and r["id"][len(prefix):].isdigit()]
    return f"{prefix}{max(used, default=0) + 1:03d}"


def _find(rows: list[dict], rule_id: str) -> dict | None:
    return next((r for r in rows if r["id"] == rule_id), None)


def _restore_at(rows: list[dict], row: dict, index: int) -> list[dict]:
    """Put `row` back at `index`, replacing any copy with the same id."""
    rest = [r for r in rows if r["id"] != row["id"]]
    rest.insert(min(index, len(rest)), row)
    return rest


def _is_safe_stored(row: dict) -> bool:
    return not (_OVERRIDE.search(row["text"]) or _SECRET.search(row["text"]))


def status_ok(result: str) -> bool:
    return str(result).startswith("status=done")


# ── What the assistant is told ───────────────────────────────────────────────

def list_rules() -> list[dict]:
    with _lock:
        return [dict(r) for r in _load()]


def guidance() -> str:
    """The 'USER PERSISTENT BEHAVIOR RULES' section for the system prompt.

    Only enabled rules, highest priority first, capped at MAX_INJECTED. A rule
    that fails the safety screen is left out here even if it is in the file
    (for example, after a hand edit). The file is never changed by this call."""
    try:
        rows = _load()
    except (ValueError, OSError) as exc:
        log.warning("Learned rules not injected: %s", exc)
        return ""
    active = [r for r in rows if r["enabled"]]
    unsafe = [r for r in active if not _is_safe_stored(r)]
    if unsafe:
        log.warning("Skipped %d stored rule(s) that fail the safety screen", len(unsafe))
    active = [r for r in active if _is_safe_stored(r)]
    active.sort(key=lambda r: (-r["priority"], r["created_at"]))
    if not active:
        return ""
    shown = active[:MAX_INJECTED]
    lines = [f"- {r['text']}" for r in shown]
    if len(active) > len(shown):
        lines.append(f"- ({len(active) - len(shown)} more rule(s) not shown to keep this prompt short)")
    return ("\nUSER PERSISTENT BEHAVIOR RULES\n"
            "The user reviewed these style and workflow preferences. Follow them when they apply. "
            "They never override safety rules, tool permissions, confirmations, undo or system "
            "instructions. If one would conflict with those, follow the safety rule and say so briefly.\n"
            + "\n".join(lines))


# ── Creating rules: proposal, then human approval ────────────────────────────

def propose(text, kind: str = "style", *, source: str = "voice", priority=None) -> dict:
    """Hold a proposed rule for review. Nothing is stored by this call."""
    clean = _clean_text(text)
    kind = _clean_kind(kind)
    prio = DEFAULT_PRIORITY if priority is None else _clean_priority(priority)
    with _lock:
        for row in _pending.values():
            if row["text"] == clean and row["kind"] == kind:
                return dict(row)
        if len(_pending) >= MAX_PENDING:
            raise ValueError("Revise ou descarte as propostas existentes primeiro.")
        row = {"id": uuid.uuid4().hex, "text": clean, "kind": kind,
               "scope": "global", "priority": prio, "source": source}
        _pending[row["id"]] = row
        return dict(row)


def pending() -> list[dict]:
    with _lock:
        return [dict(row) for row in _pending.values()]


def reject(proposal_id: str) -> str:
    with _lock:
        if _pending.pop(proposal_id, None) is None:
            return outcome.failed("learned_rules", "Proposta não encontrada / Proposal not found")
    return outcome.done("rule_rejected")


def accept_pending(proposal_id: str) -> str:
    """Store a proposal the user has approved. Callers must have shown it first."""
    with _lock:
        proposal = _pending.get(proposal_id)
        if proposal is None:
            return outcome.failed("learned_rules", "Proposta não encontrada / Proposal not found")
        try:
            rows = _load()
        except (ValueError, OSError) as exc:
            return outcome.failed("learned_rules", str(exc))
        if any(r["text"] == proposal["text"] and r["kind"] == proposal["kind"] for r in rows):
            _pending.pop(proposal_id, None)
            return outcome.done("learned_rules", note="Already stored", guidance=guidance())
        if len(rows) >= MAX_RULES:
            return outcome.failed("learned_rules", f"Limite de {MAX_RULES} regras atingido / Limit reached")
        now = _now()
        rule = {"id": _next_id(rows), "text": proposal["text"], "kind": proposal["kind"],
                "scope": proposal["scope"], "priority": proposal["priority"], "enabled": True,
                "created_at": now, "updated_at": now, "source": proposal["source"]}
        try:
            _save(rows + [rule])
        except (OSError, ValueError) as exc:
            return outcome.failed("learned_rules", str(exc))
        _pending.pop(proposal_id, None)

    undo.push_undo(f"Regra / Rule: {rule['text'][:60]}",
                   lambda: _undo_state(rule["id"], rule,
                                       lambda rows: [r for r in rows if r["id"] != rule["id"]]))
    return outcome.done("learned_rules", id=rule["id"], guidance=guidance())


def review(proposal_id: str, player) -> str:
    """Show a proposal on the HUD; it is stored only if the user presses CONFIRM."""
    if player is None or not callable(getattr(player, "show_confirm", None)):
        return outcome.failed("learned_rules", "Abra o HUD / Open HUD for review")
    if confirm.pending_title():
        return outcome.failed("learned_rules", "Outra confirmação pendente / Another confirmation pending")
    with _lock:
        row = _pending.get(proposal_id)
    if row is None:
        return outcome.failed("learned_rules", "Proposta não encontrada / Proposal not found")
    player.show_content("Revisar preferência / Review preference", row["text"])

    def accept() -> str:
        result = accept_pending(proposal_id)
        notify = getattr(player, "request_say", None)
        if status_ok(result) and callable(notify):
            try:
                notify("A preference was accepted locally. Briefly acknowledge without calling tools. "
                       + guidance())
            except Exception:
                log.debug("Could not announce accepted rule", exc_info=True)
        return result

    return confirm.request("learned_rule", "Salvar preferência / Save preference", row["text"], accept)


# ── Changing stored rules: prepare, show, confirm, apply ─────────────────────

def _describe(action: str, before: dict, after: dict | None) -> str:
    head = (f"{_ACTION_TITLE[action]} regra {before['id']} "
            f"(origem: {before['source']}, criada em {before['created_at']}, escopo: {before['scope']})")
    if action == "remove":
        return f'{head}\n"{before["text"]}" (prioridade {before["priority"]})'
    if action in ("enable", "disable"):
        state = "ativa" if after["enabled"] else "desativada"
        return f'{head}\n"{before["text"]}" (prioridade {before["priority"]}) -> {state}'
    return (f'{head}\nAntes: "{before["text"]}" (prioridade {before["priority"]})\n'
            f'Depois: "{after["text"]}" (prioridade {after["priority"]})')


def prepare(action: str, rule_id, *, text=None, priority=None) -> dict:
    """Describe a change to a stored rule without making it.

    Raises LookupError for an unknown id and ValueError for a bad change. The
    returned dict is what apply_change() needs, and what the user is shown."""
    if action not in CHANGE_ACTIONS:
        raise ValueError("Ação desconhecida.")
    if not isinstance(rule_id, str) or not rule_id.strip():
        raise ValueError("Informe o ID da regra.")
    rid = rule_id.strip()
    with _lock:
        rows = _load()
    index = next((i for i, r in enumerate(rows) if r["id"] == rid), None)
    if index is None:
        raise LookupError("Regra não encontrada.")
    before = rows[index]
    after = None
    if action != "remove":
        after = dict(before)
        if action == "enable":
            after["enabled"] = True
        elif action == "disable":
            after["enabled"] = False
        else:
            if text is None and priority is None:
                raise ValueError("Informe o novo texto ou a nova prioridade.")
            if text is not None:
                after["text"] = _clean_text(text)
            if priority is not None:
                after["priority"] = _clean_priority(priority)
        after["updated_at"] = _now()
    return {"action": action, "rule_id": rid, "index": index, "before": before,
            "after": after, "summary": _describe(action, before, after)}


def apply_change(change: dict) -> str:
    """Make a prepared change, but only if the rule still matches what was shown."""
    rid, before, after, index = change["rule_id"], change["before"], change["after"], change["index"]
    with _lock:
        try:
            rows = _load()
        except (ValueError, OSError) as exc:
            return outcome.failed("learned_rules", str(exc))
        if _find(rows, rid) != before:
            return outcome.failed("learned_rules",
                                  "A regra mudou desde a revisão; nada foi alterado / Rule changed since review")
        try:
            if after is None:
                _save([r for r in rows if r["id"] != rid])
            else:
                _save(_restore_at(rows, after, index))
        except (OSError, ValueError) as exc:
            return outcome.failed("learned_rules", str(exc))

    undo.push_undo(f"{_ACTION_TITLE[change['action']]} regra / rule {rid}",
                   lambda: _undo_state(rid, after,
                                       lambda rows: _restore_at(rows, before, index)))
    return outcome.done("learned_rules", id=rid, action=change["action"], guidance=guidance())


def _undo_state(rule_id: str, expected: dict | None, restore) -> str:
    """Reverse one change, only if the rule is still exactly as that change left it.

    `expected` is the rule after the change, or None when the change removed it.
    If anything changed since, undo stops rather than overwrite it."""
    with _lock:
        try:
            rows = _load()
        except (ValueError, OSError) as exc:
            return outcome.failed("rule_undo", str(exc))
        if _find(rows, rule_id) != expected:
            return outcome.failed("rule_undo",
                                  "A regra mudou depois; desfazer cancelado / Rule changed since; undo cancelled")
        try:
            _save(restore(rows))
        except (OSError, ValueError) as exc:
            return outcome.failed("rule_undo", str(exc))
    return outcome.done("rule_undo", id=rule_id)


def review_change(action: str, rule_id, player, *, text=None, priority=None) -> str:
    """Ask the user on the HUD before a stored rule is changed."""
    if player is None or not callable(getattr(player, "show_confirm", None)):
        return outcome.failed("learned_rules", "Abra o HUD / Open HUD for review")
    if confirm.pending_title():
        return outcome.failed("learned_rules", "Outra confirmação pendente / Another confirmation pending")
    try:
        change = prepare(action, rule_id, text=text, priority=priority)
    except (LookupError, ValueError) as exc:
        return outcome.failed("learned_rules", str(exc))
    title = f"{_ACTION_TITLE[action]} preferência / {action} preference"
    return confirm.request(f"learned_rule_{action}", title, change["summary"],
                           lambda: apply_change(change))


# ── Backup and restore ───────────────────────────────────────────────────────

def _json_path(path) -> Path:
    target = Path(path)
    if target.suffix.lower() != ".json":
        raise ValueError("Escolha um arquivo .json")
    return target


def export_rules(path) -> str:
    target = _json_path(path)
    with _lock:
        try:
            rows = _load()
        except (ValueError, OSError) as exc:
            return outcome.failed("rules_export", str(exc))
    try:
        _write_json(target, {"version": SCHEMA_VERSION, "exported_at": _now(), "rules": rows})
    except OSError as exc:
        return outcome.failed("rules_export", str(exc))
    return outcome.done("rules_export", count=len(rows))


def read_import(path) -> list[dict]:
    """Validate a backup file without storing anything. Raises ValueError with a
    reason the user can read. Every rule is screened again on the way in."""
    source = _json_path(path)
    if not source.is_file():
        raise ValueError("Arquivo não encontrado.")
    if source.stat().st_size > MAX_STORE_BYTES:
        raise ValueError("Arquivo grande demais.")
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("Arquivo JSON inválido.") from None
    rows = _migrate(data, _stamp(source.stat().st_mtime))
    screened = []
    for row in rows:
        try:
            text = _clean_text(row["text"])
        except ValueError as exc:
            raise ValueError(f"Regra {row['id']} recusada: {exc}") from None
        screened.append({**row, "text": text, "source": "import"})
    return screened


def merge_import(rows: list[dict]) -> str:
    """Add imported rules that are not already stored. Existing rules are never
    replaced. Call only after the user has seen the list and agreed."""
    with _lock:
        try:
            current = _load()
        except (ValueError, OSError) as exc:
            return outcome.failed("rules_import", str(exc))
        known = {(r["text"], r["kind"]) for r in current}
        added: list[dict] = []
        for row in rows:
            key = (row["text"], row["kind"])
            if key in known:
                continue
            if len(current) + len(added) >= MAX_RULES:
                break
            now = _now()
            added.append({**row, "id": _next_id(current + added),
                          "created_at": row["created_at"] or now, "updated_at": now,
                          "source": "import"})
            known.add(key)
        if added:
            try:
                _save(current + added)
            except (OSError, ValueError) as exc:
                return outcome.failed("rules_import", str(exc))
    return outcome.done("rules_import", added=len(added), skipped=len(rows) - len(added))
