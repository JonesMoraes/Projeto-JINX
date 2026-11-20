"""
JINX action — autonomy_control: the operator console for the autonomy layer.

Every state change the user can ask for by voice lives here. The destructive
ACL and the deny floor (core/autonomy.py) deliberately have no voice switch:
only human hands weaken them, in the settings.

Gate rules this tool inherits (it goes through ActionRegistry.run like any
other action): running a queued destructive item is itself audited and shown
in the log, and the queue refuses to spend more than the configured daily
budget — which defaults to ZERO, so nothing destructive ever runs from the
queue until this user explicitly raises it.
"""
from core import outcome

TOOL = {
    "name": "autonomy_control",
    "description": ("Console de autonomia da JINX: status; nível 0-3 (0=pausado, 3=autônomo); "
                    "pause/resume; budget N (orçamento diário de ações destrutivas, default 0); "
                    "queue (listar ações irreversíveis em espera); run N (executar item N da fila "
                    "(executar item N da fila — apenas com pedido EXPLÍCITO do usuário); "
                    "controles da memória observada: episodic on/off, screen on/off, "
                    "interval N segundos, forget N dias)."),
    "parameters": {"type": "OBJECT", "properties": {
        "mode": {"type": "STRING",
                 "enum": ["status", "level", "pause", "resume", "budget", "queue",
                          "run", "forget", "episodic", "screen", "interval"]},
        "value": {"type": "STRING",
                  "description": "Argumento do modo: nível (0-3), índice da fila, dias, on/off, segundos."},
    }, "required": ["mode"]},
    "behavior": "BLOCKING",
    "tier": "core",
    "brief": "Console de autonomia: nível, pausa, fila, memória observada",
}


def _handler(parameters, session_memory=None):
    from core import autonomy
    from memory import episodic

    mode = str(parameters.get("mode", "status")).strip().lower()
    value = str(parameters.get("value", "")).strip()

    if mode == "status":
        return _status(autonomy, episodic)

    if mode == "level":
        try:
            autonomy.set_level(int(value))
        except (TypeError, ValueError):
            return outcome.failed("autonomy_level", "O nível deve ser 0, 1, 2 ou 3.")
        return outcome.done("autonomy_level", level=autonomy.level_name())

    if mode == "pause":
        return outcome.done("autonomy_pause", resposta=autonomy.pause())

    if mode == "resume":
        return outcome.done("autonomy_resume", resposta=autonomy.resume())

    if mode == "budget":
        try:
            n = autonomy.set_budget(int(value))
        except (TypeError, ValueError):
            return outcome.failed("autonomy_budget", "Informe um número entre 0 e 20.")
        return outcome.done("autonomy_budget", orcamento=n)

    if mode == "queue":
        rows = autonomy.queue_list()
        if not rows:
            return outcome.done("autonomy_queue", resposta="Fila vazia.")
        listing = "\n".join(f"{i + 1}. {row['name']} ({row['reason']})"
                            for i, row in enumerate(rows))
        return outcome.done("autonomy_queue", fila=listing)

    if mode == "run":
        return _run_queued(autonomy, value)

    if mode == "forget":
        try:
            return outcome.done("episodic_forget", resposta=episodic.forget(int(value or 1)))
        except (TypeError, ValueError):
            return outcome.failed("episodic_forget", "Informe um número de dias.")

    if mode == "episodic":
        on = value.lower() != "off"
        episodic.configure(enabled=on)
        if on:
            episodic.ensure_started()
        return outcome.done("episodic_toggle", resposta=(
            "Memória observada ATIVADA." if on else "Memória observada desativada."))

    if mode == "screen":
        on = value.lower() == "on"
        episodic.configure(screen=on)
        return outcome.done("episodic_screen", resposta=(
            "Capturas de tela ATIVADAS." if on else "Capturas de tela desativadas."))

    if mode == "interval":
        try:
            cfg = episodic.configure(interval=float(value or 60))
        except (TypeError, ValueError):
            return outcome.failed("episodic_interval", "Informe um intervalo em segundos.")
        return outcome.done("episodic_interval", intervalo=f"{cfg['interval']:.0f}s")

    return outcome.failed("autonomy_mode", "Modo desconhecido.")


def _status(autonomy, episodic) -> str:
    cfg = autonomy._cfg()
    paused = autonomy._paused(cfg)
    lines = [f"Nível {cfg['level']} ({autonomy.level_name()})"]
    if paused:
        lines.append(f"pausada até {cfg['paused_until'][:16]}")
    lines.append(f"orçamento destrutivas/dia: {cfg['budget']}")
    lines.append(f"fila pendente: {len(autonomy.queue_list())}")
    ep = episodic.status()
    lines.append(f"memória observada: {'on' if ep['enabled'] else 'off'} "
                 f"(screen {'on' if ep['screen'] else 'off'}, intervalo {ep['interval']:.0f}s, "
                 f"{ep['events']} eventos, {ep['episodes']} episódios)")
    return outcome.done("autonomy_status", status=" · ".join(lines))


def _run_queued(autonomy, value: str) -> str:
    from core.action_loader import active_registry
    from core.autonomy import queue_run

    registry = active_registry()
    if registry is None:
        return outcome.unverified("autonomy_queue_run",
                                  "O registro de tools ainda não foi descoberto.")

    rows = autonomy.queue_list()
    try:
        index = int(value or 1)
    except (TypeError, ValueError):
        if not rows:
            return outcome.done("autonomy_queue_run", resposta="Fila vazia.")
        listing = "\n".join(f"{i + 1}. {row['name']} ({row['reason']})"
                            for i, row in enumerate(rows))
        return outcome.ask("autonomy_queue_run", "Informe o número do item a executar:\n" + listing)
    if not 1 <= index <= len(rows):
        return outcome.failed("autonomy_queue_run", "Item não encontrado na fila.")

    def runner() -> str:
        entry = autonomy.queue_list()
        # Re-list inside runner: the queue may have changed while waiting.
        # queue_run already validated the index against the same snapshot above,
        # so a mismatch here is rare; guard it rather than index past the end.
        if index <= len(entry):
            chosen = entry[index - 1]
            # run_direct re-checks the deny floor and executes past the queue
            # branch, so the row cannot re-queue itself in a loop.
            return autonomy.run_direct(registry.run, str(chosen["name"]),
                                       dict(chosen.get("parameters") or {}))
        return "Item da fila não existe mais."

    return queue_run(index, runner)


TOOL["handler"] = _handler
