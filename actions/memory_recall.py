"""
JINX action — memory_recall: consult what was observed before doing something.

The model is told to call this BEFORE improvising a task the user says it has
done together before ("igual da última vez", "como ontem"). It returns a
bounded, redacted, untrusted-labelled context block of digests and events so
the assistant can propose to repeat the routine — and say where the memory
came from, so the user sees WHY JINX did it that way.

This tool only READS. Rules and skills born from what it surfaces still go
through the human-approved paths (learned_rules propose/review; skill_forge).
"""
from core import outcome

TOOL = {
    "name": "memory_recall",
    "description": ("Memória observada da JINX: consulte ANTES de improvisar uma tarefa que o "
                    "usuário diz que você já fez antes ('igual da última vez', 'como ontem'). "
                    "mode=recall tenta lembrar; mode=digest comprime um dia de observações e "
                    "pode propor regras (sempre com aprovação do usuário no HUD)."),
    "parameters": {"type": "OBJECT", "properties": {
        "mode": {"type": "STRING", "enum": ["recall", "digest"]},
        "query": {"type": "STRING", "description": "O que procurar (para recall)"},
        "day": {"type": "STRING", "description": "AAAA-MM-DD (para digest; vazio = hoje)"},
        "k": {"type": "NUMBER", "description": "Máximo de lembranças (1-10, default 5)"},
    }, "required": ["mode"]},
    "behavior": "BLOCKING",
    "tier": "extra",
    "brief": "Consultar memória observada ('igual da última vez')",
}


def _handler(parameters, session_memory=None):
    from memory import episodic

    mode = str(parameters.get("mode", "recall")).strip().lower()
    if mode == "recall":
        return outcome.done("memory_recall", memoria=episodic.recall(
            str(parameters.get("query", "")), int(parameters.get("k", 5) or 5)))
    if mode == "digest":
        return outcome.done("memory_digest", resposta=episodic.digest(
            str(parameters.get("day") or "") or None))
    return outcome.failed("memory_recall", "Modo desconhecido.")


TOOL["handler"] = _handler
