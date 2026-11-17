"""Process inspection and asynchronous shutdown with identity verification."""
from dataclasses import dataclass
import json
import os
import platform
import threading
import time
import psutil
from core import appidentity, confirm, outcome

_attempts = set()
_lock = threading.Lock()
_CRITICAL = {"system", "registry", "smss.exe", "csrss.exe", "wininit.exe",
             "winlogon.exe", "services.exe", "lsass.exe"}


@dataclass(frozen=True)
class Target:
    pid: int
    created: float
    name: str
    exe: str


def _snapshots():
    rows = {}
    for process in psutil.process_iter(["pid", "name", "memory_info", "cpu_times", "create_time"]):
        try:
            info = process.info
            cpu = info.get("cpu_times")
            memory = info.get("memory_info")
            if not cpu or not memory:
                continue
            rows[info["pid"]] = {"pid": info["pid"], "name": str(info.get("name") or "?"),
                "created": info["create_time"], "rss": memory.rss, "seconds": cpu.user + cpu.system}
        except (psutil.Error, KeyError, AttributeError):
            continue
    return rows


def inspect_processes(metric="ram", limit=10, pid=None, name=""):
    if metric not in ("ram", "cpu") or not 1 <= limit <= 20:
        raise ValueError("metric/limit")
    first = _snapshots()
    start = time.monotonic()
    if metric == "cpu":
        time.sleep(.25)
        rows = _snapshots()
    else:
        rows = first
    elapsed = max(.001, time.monotonic() - start)
    capacity = max(1, psutil.cpu_count() or 1)
    output = []
    for process_id, row in rows.items():
        if pid is not None and process_id != pid:
            continue
        if name and os.path.splitext(row["name"])[0].casefold() != os.path.splitext(name)[0].casefold():
            continue
        item = {"pid": process_id, "name": row["name"], "ram_mib": round(row["rss"] / 1048576, 2)}
        if metric == "cpu":
            before = first.get(process_id)
            if not before or before["created"] != row["created"]:
                continue
            item["cpu_total_percent"] = round(min(100., max(0., (row["seconds"] - before["seconds"]) / elapsed * 100 / capacity)), 2)
        output.append(item)
    return sorted(output, key=lambda row: rows[row["pid"]]["rss"] if metric == "ram" else row["cpu_total_percent"], reverse=True)[:limit]


def _guard(target):
    # Re-check identity immediately before acting; process IDs can be reused.
    if target.pid <= 4 or target.name.casefold() in _CRITICAL:
        raise ValueError("Processo crítico protegido / Critical process protected")
    if target.pid == os.getpid() or target.pid in appidentity.own_pids():
        raise ValueError("Processo do JINX protegido / JINX process protected")
    process = psutil.Process(target.pid)
    if process.create_time() != target.created or os.path.normcase(process.exe()) != os.path.normcase(target.exe):
        raise ValueError("Identidade mudou; solicite novamente / Identity changed; request again")
    if not target.exe or os.path.normcase(target.exe) in appidentity.own_exes():
        raise ValueError("Executável protegido ou não identificado / Protected or unidentified executable")
    return process


def _targets(pid=None, name=""):
    if pid is not None:
        candidates = [psutil.Process(pid)]
    else:
        if not name:
            raise ValueError("Informe nome ou PID / Provide name or PID")
        # Exact process names and existing aliases only, never window-title guesses.
        matches = appidentity.running(name, include_self=True)
        matches = [m for m in matches if m.score >= 100]
        groups = {os.path.splitext(m.name)[0].casefold() for m in matches}
        if len(groups) != 1:
            raise ValueError("Nome ausente ou ambíguo; liste processos e use o PID / Name missing or ambiguous; list processes and use PID")
        candidates = [psutil.Process(m.pid) for m in matches]
    targets = []
    for process in candidates:
        target = Target(process.pid, process.create_time(), process.name(), process.exe())
        _guard(target)
        targets.append(target)
    if not targets:
        raise ValueError("Nenhum processo encontrado / No process found")
    if len(targets) > 30:
        raise ValueError("Muitos processos; escolha um PID / Too many processes; choose a PID")
    return tuple(targets)


def _gone(target):
    try:
        process = psutil.Process(target.pid)
        return not process.is_running() or process.create_time() != target.created
    except psutil.NoSuchProcess:
        return True


def _wait(target, seconds=2):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if _gone(target):
            return True
        time.sleep(.1)
    return _gone(target)


def _close(target):
    process = _guard(target)
    if platform.system() == "Windows":
        # Do not use Process.terminate on Windows: it is not graceful there.
        requested = appidentity._post_close_windows(target.pid) > 0
    else:
        process.terminate()  # POSIX SIGTERM; completion is checked below.
        requested = True
    with _lock:
        _attempts.add((target.pid, target.created))
    if requested and _wait(target):
        return outcome.done("process_close", pid=target.pid)
    return outcome.unverified("process_close", "Continua aberto ou não tem janela; nada foi forçado / Still open or no window; nothing forced", pid=target.pid)


def _force(target):
    with _lock:
        attempted = (target.pid, target.created) in _attempts
    if not attempted:
        return outcome.failed("process_force", "Peça o fechamento normal primeiro / Request graceful close first")
    process = _guard(target)
    process.kill()
    if _wait(target):
        return outcome.done("process_force", pid=target.pid)
    return outcome.unverified("process_force", "Processo ainda não confirmou saída / Process exit not confirmed", pid=target.pid)


def _set_priority(target, requested):
    """Set a portable priority and register a guarded restore in the undo journal."""
    process = _guard(target)
    old = process.nice()
    name = str(requested or "").strip().lower().replace(" ", "_")
    if platform.system() == "Windows":
        priorities = {"idle": psutil.IDLE_PRIORITY_CLASS,
                      "below_normal": psutil.BELOW_NORMAL_PRIORITY_CLASS,
                      "normal": psutil.NORMAL_PRIORITY_CLASS,
                      "above_normal": psutil.ABOVE_NORMAL_PRIORITY_CLASS,
                      "high": psutil.HIGH_PRIORITY_CLASS}
        if name not in priorities:
            return outcome.failed("process_priority", "Use idle, below_normal, normal, above_normal, or high.")
        value = priorities[name]
    else:
        try:
            value = int(requested)
        except (TypeError, ValueError):
            return outcome.failed("process_priority", "On POSIX, nice must be an integer from 0 to 19.")
        if not 0 <= value <= 19:
            return outcome.failed("process_priority", "Only nice values 0–19 are accepted.")
    try:
        process.nice(value)
        actual = process.nice()
        if actual != value:
            process.nice(old)
            return outcome.unverified("process_priority", "The requested priority did not verify.", pid=target.pid)
        from core.undo import push_undo
        def restore():
            current = _guard(target)
            if current.nice() != actual:
                return outcome.failed("process_priority_undo", "Priority changed since; left untouched.", pid=target.pid)
            current.nice(old)
            return outcome.done("process_priority_undo", pid=target.pid)
        push_undo(f"Process priority: {target.name}", restore)
        return outcome.done("process_priority", pid=target.pid, priority=name or value, verified=True)
    except (psutil.Error, OSError, ValueError) as exc:
        return outcome.failed("process_priority", str(exc), pid=target.pid)


def _set_affinity(target, requested):
    """Set logical CPU affinity and register a guarded restore."""
    if not isinstance(requested, list) or not requested:
        return outcome.failed("process_affinity", "cpus must be a non-empty list of indexes.")
    if any(isinstance(cpu, bool) or not isinstance(cpu, int) for cpu in requested):
        return outcome.failed("process_affinity", "CPU indexes must be integers.")
    cpus = sorted(set(requested))
    if len(cpus) != len(requested) or any(cpu < 0 for cpu in cpus):
        return outcome.failed("process_affinity", "Indexes must be unique and non-negative.")
    try:
        process = _guard(target)
        old = sorted(process.cpu_affinity())
        process.cpu_affinity(cpus)
        actual = sorted(process.cpu_affinity())
        if actual != cpus:
            process.cpu_affinity(old)
            return outcome.unverified("process_affinity", "Requested affinity did not verify.", pid=target.pid)
        from core.undo import push_undo
        def restore():
            current = _guard(target)
            if sorted(current.cpu_affinity()) != actual:
                return outcome.failed("process_affinity_undo", "Affinity changed since; left untouched.", pid=target.pid)
            current.cpu_affinity(old)
            return outcome.done("process_affinity_undo", pid=target.pid)
        push_undo(f"Process affinity: {target.name}", restore)
        return outcome.done("process_affinity", pid=target.pid, cpus=cpus, verified=True)
    except (psutil.Error, OSError, ValueError) as exc:
        return outcome.failed("process_affinity", str(exc), pid=target.pid)


def _perform(targets, force=False):
    results = []
    for target in targets:
        try:
            result = _force(target) if force else _close(target)
        except psutil.NoSuchProcess:
            result = outcome.unverified("process_close", "Processo já havia saído / Process already exited", pid=target.pid)
        except (psutil.Error, ValueError):
            result = outcome.failed("process_close", "Proteção, acesso negado ou identidade mudou / Protected, access denied or identity changed", pid=target.pid)
        results.append(result)
    ok = all(result.startswith("status=done ") for result in results)
    return (outcome.done("process_manager", results=results) if ok else
            outcome.unverified("process_manager", "Nem todas as saídas foram confirmadas / Not all exits confirmed", results=results))


def process_manager(parameters, player=None, **_context):
    p = parameters or {}
    try:
        action = p.get("action", "top")
        pid = p.get("pid")
        if pid is not None and (isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0):
            raise ValueError("PID inválido / Invalid PID")
        name = str(p.get("name") or "").strip()
        if action in ("top", "details"):
            rows = inspect_processes(p.get("metric", "ram"), int(p.get("limit", 10)), pid, name)
            if not rows:
                return outcome.unverified("process_manager", "Nenhum processo legível corresponde / No readable process matches")
            text = "\n".join(f"PID {r['pid']} | {r['name']} | {r['ram_mib']} MiB" +
                (f" | CPU {r['cpu_total_percent']}%" if "cpu_total_percent" in r else "") for r in rows)
            if player and callable(getattr(player, "show_content", None)):
                player.show_content("Processos / Processes", text)
            return outcome.done("process_manager", data=outcome.untrusted("process-table", json.dumps(rows, ensure_ascii=False)),
                note="CPU: parcela da capacidade total; RAM: RSS por processo, não some memória compartilhada / CPU normalized to total capacity; RSS may include shared memory")
        if action in ("priority", "affinity"):
            targets = _targets(pid, name)
            if len(targets) != 1:
                raise ValueError("Choose one process by PID or exact name")
            return (_set_priority(targets[0], p.get("priority")) if action == "priority"
                    else _set_affinity(targets[0], p.get("cpus")))
        if action not in ("close", "force"):
            raise ValueError("Ação inválida / Invalid action")
        targets = _targets(pid, name)
        if action == "force":
            with _lock:
                if any((t.pid, t.created) not in _attempts for t in targets):
                    return outcome.failed("process_force", "Tente close primeiro / Try close first")
        summary = ", ".join(f"{t.name} (PID {t.pid})" for t in targets)
        return confirm.request("process_manager", "Forçar encerramento / Force quit" if action == "force" else "Fechar processo / Close process",
            summary + " — trabalho não salvo pode ser perdido / unsaved work may be lost",
            lambda: _perform(targets, action == "force"))
    except (ValueError, psutil.Error):
        return outcome.failed("process_manager", "Não foi possível selecionar/inspecionar o alvo / Could not select or inspect target")
    except Exception:
        return outcome.failed("process_manager", "Consulta/operação não confirmada / Query or operation unverified")


TOOL = {"name": "process_manager", "description": "List top CPU/RAM processes or details. Close and force run asynchronously. Force requires a previous graceful attempt. Protects JINX and critical OS processes. No undo for termination.",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["top", "details", "close", "force", "priority", "affinity"]},
        "metric": {"type": "STRING", "enum": ["ram", "cpu"]},
        "name": {"type": "STRING", "description": "Exact application/process name"},
        "pid": {"type": "INTEGER"}, "limit": {"type": "INTEGER", "description": "1–20; default 10"},
        "priority": {"type": "STRING", "description": "Windows: idle/below_normal/normal/above_normal/high; POSIX: nice 0–19"},
        "cpus": {"type": "ARRAY", "items": {"type": "INTEGER"}, "description": "Logical CPU indexes"}},
        "required": ["action"]}, "handler": process_manager, "tier": "extra", "brief": "Inspect CPU/RAM; asynchronous close/force; JINX protected."}
