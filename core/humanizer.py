"""
Humanizer — turns model-written text into something a voice can say.

The local pipeline (`providers/engine_pipeline.py`) feeds LLM output to a TTS
engine literally. A text model answers in writing: `**negrito**`, `## Título`,
listas com traços, cercas de código and the trained-in openers of a chat
assistant ("Claro!", "Perfeito!", "Espero ter ajudado"). None of that was
written to be read aloud — espeak reads the asterisks, a fence unreadable and
a closer nobody would say to someone standing next to them.

`humanize()` is a deterministic, regex-only pass applied on the way to the
voice ONLY. The conversation history keeps the model's original answer: these
edits are for the ear, not a correction of what the model said, and the next
turn must still see the answer the model actually wrote.

Design rules, learned the hard way elsewhere in this project
(see `_UNSPEAKABLE` in providers/engine_pipeline.py):
- Every range and pattern is narrow on purpose. A broad "strip formatting"
  regex eats CJK text, versions like 1.2.3 and file names like sdk_v2.
- Every step is wrapped so a bad pass returns the input unchanged rather
  than an empty string. Silence is the one failure a voice assistant cannot
  come back from.
"""
from __future__ import annotations

import re

__all__ = ["humanize"]

# ── fenced code ──────────────────────────────────────────────────────────────
# A voice reading Python aloud is worse than a pause. A closed fence is
# dropped whole; an unclosed one (a truncated reply) is dropped to the end,
# because whatever follows it is code the marker never released.
_FENCE_RE = re.compile(r"```[^\n]*\n.*?```|```.*", re.S)

# ── writing that is not speech ───────────────────────────────────────────────
_HEADER_RE   = re.compile(r"^\s{0,3}#{1,6}\s+", re.M)        # ## Heading
_QUOTE_RE    = re.compile(r"^\s{0,3}>+\s?", re.M)            # > blockquote
_BULLET_RE   = re.compile(r"^\s{0,3}[-*•·+]\s+", re.M)       # - bullet item
_NUMITEM_RE  = re.compile(r"^\s{0,3}\d{1,2}[.)]\s+", re.M)   # 1. numbered item
_TABLESEP_RE = re.compile(r"^\s*\|?[\s:|-]{3,}\|?\s*$", re.M)  # |---|---|
_PIPE_RE     = re.compile(r"\s*\|\s*")                        # table cell bars

_LINK_RE     = re.compile(r"\[([^\]\n]{0,80})\]\((https?://[^)\s]+)\)")
_BARE_URL_RE = re.compile(r"(?<!\S)(https?://\S{8,})")

# `**bold**` before single `*italic*`, or one asterisk eats the other's pair.
_BOLD_RE     = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
_ITALIC_RE   = re.compile(r"\*(?=\S)([^*\n]+?)(?<=\S)\*")
_BACKTICK_RE = re.compile(r"`([^`\n]+)`")

# ── chat-assistant openers and closers ──────────────────────────────────────
# Filler the model reaches for to be polite. Only matched at the edges of a
# sentence — an opener mid-sentence is often load-bearing ("Com certeza ele
# já saiu") and must survive.
_OPENERS = (
    "Claro!", "Com certeza!", "Perfeito!", "Ótimo!", "Beleza!", "Vamos lá!",
    "Sure!", "Certainly!", "Of course!", "Great question!",
    "Excellent question!", "That's a great question!",
)
_CLOSERS = (
    "Espero ter ajudado!", "Espero ter ajudado.", "Não hesite em perguntar!",
    "Não hesite em perguntar.", "Fico à disposição!", "Fico à disposição.",
    "Estou à disposição!", "Estou à disposição.",
    "Não hesite em me perguntar se precisar de mais alguma coisa.",
    "I hope this helps!", "Hope that helps!",
    "Let me know if you have any questions!",
    "Don't hesitate to reach out!", "Feel free to ask!",
)
_AS_AI = re.compile(
    r"(?i)^como uma? (inteligência artificial|IA|modelo de linguagem|assistente virtual)\s*,?\s*"
    r"|^as an ai (?:language model|assistant)[,:]?\s*")


# ── config switch ────────────────────────────────────────────────────────────
# Read once, lazily: this runs before every spoken sentence and the config
# file must not be re-read that often. A failing read keeps the humanizer ON.
_ON: bool | None = None


def _enabled() -> bool:
    global _ON
    if _ON is None:
        try:
            from memory import config_manager
            _ON = config_manager.get_humanizer_enabled()
        except Exception:
            _ON = True
    return _ON


def _edge_patterns(phrases) -> str:
    """Match each phrase only at a sentence edge: reply start or after
    `.`, `!`, `?` and one space — never the middle of a sentence."""
    return "|".join(re.escape(p) for p in phrases)


_OPENER_RE = re.compile(r"(?:^|(?<=[.!?]) )(" + _edge_patterns(_OPENERS) + r")\s*")
_CLOSER_RE = re.compile(r"\s*(" + _edge_patterns(_CLOSERS) + r")(?=\s*$|[.!?]|$)")


def _strip_markdown(s: str) -> str:
    s = _HEADER_RE.sub("", s)
    # A header glued after other removed formatting: "Claro! ## Resultado".
    # Needs whitespace before, so "C# programação" and "#hashtag" survive.
    s = re.sub(r"(?<=\s)#{1,6}\s+(?=\S)", "", s)
    s = _QUOTE_RE.sub("", s)
    s = _BULLET_RE.sub("", s)
    s = _NUMITEM_RE.sub("", s)
    s = _TABLESEP_RE.sub(" ", s)
    # [label](url) → label; a link with no label says nothing and is dropped.
    s = _LINK_RE.sub(lambda m: m.group(1) if m.group(1) else " ", s)
    # A bare URL is unreadable aloud; the target is in the log and the
    # transcript, not in a TTS engine spelling "https dois pontos barra barra".
    s = _BARE_URL_RE.sub(" ", s)
    s = _BOLD_RE.sub(r"\1", s)
    s = _ITALIC_RE.sub(r"\1", s)
    s = _BACKTICK_RE.sub(r"\1", s)
    # Table rows survive as their cells joined, which reads as a list.
    s = _PIPE_RE.sub(", ", s)
    return s


def humanize(text: str | None) -> str:
    """Return `text` in a form safe — and natural — to read aloud."""
    if not text or not text.strip():
        return ""
    if not _enabled():
        return text
    s = text
    for step in (
        lambda t: _FENCE_RE.sub(" ", t),   # code, first: nothing inside survives
        _strip_markdown,
        lambda t: _AS_AI.sub("", t),
        lambda t: _OPENER_RE.sub("", t),
        lambda t: _CLOSER_RE.sub("", t),
    ):
        try:
            s2 = step(s)
        except Exception:
            continue                        # a step failing never empties the reply
        if s2 and s2.strip():
            s = s2
        # An empty result means the step ATE the reply, not that it had none —
        # keep the previous state and move on.
    # Collapse what the removals left: multi-space, stray punctuation and
    # leftover list markers dangling between lines.
    s = re.sub(r"[ \t]{2,}", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    # Glue after punctuation that removals left attached: letter, comma or
    # semicolon, letter — deliberately narrower than "every marker", because
    # "oka.cmd" and "C:/Users" are not sentences and "1,5" is a decimal.
    s = re.sub(r"(?<=[A-Za-zÀ-ÿªº])[;,](?=[A-Za-zÀ-ÿ])", lambda m: m.group(0) + " ", s)
    s = re.sub(r"([!?.]){2,}", r"\1", s)
    s = re.sub(r"^\s*[-•]\s*", "", s)
    s = s.strip()
    # Removing an opener left the reply starting mid-capitalisation: "devo
    # avisar que…". A voice reading that aloud still starts a sentence, so
    # capitalise the first letter whatever the removals did.
    if s and s[0].islower():
        s = s[0].upper() + s[1:]
    return s
