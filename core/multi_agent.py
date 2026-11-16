"""Isolated multi-agent coordinator for JINX.

This module deliberately does not replace the Live session. It owns agent
selection and bounded per-agent state; main.py may use its active context when
building a new session. Profile Markdown is data only and is never executed.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Callable

from core.tasks.agents import AgentProfile, parse

_MAX_PROFILE_BYTES = 128 * 1024
_MAX_INSTRUCTIONS = 24_000
_MAX_HISTORY = 24
_MAX_TEXT = 8_000
_MAX_DEBATE_TURNS = 8


@dataclass
class AgentSession:
    """Bounded, in-memory conversation state for exactly one agent."""

    turns: deque[str] = field(default_factory=lambda: deque(maxlen=_MAX_HISTORY))

    def add(self, role: str, text: str) -> None:
        text = str(text or "")[:_MAX_TEXT]
        if text:
            self.turns.append(f"{role}: {text}")

    def reset(self) -> None:
        self.turns.clear()

    def snapshot(self) -> list[str]:
        return list(self.turns)


class AgentManager:
    """Loads profiles and coordinates explicit, reversible agent operations."""

    def __init__(self, agents_dir: Path | str):
        self._dir = Path(agents_dir)
        self._lock = RLock()
        self._profiles: dict[str, AgentProfile] = {}
        self._sessions: dict[str, AgentSession] = {}
        self._active = "jinx"
        self.reload()

    def reload(self) -> None:
        profiles: dict[str, AgentProfile] = {}
        if self._dir.is_dir():
            for path in sorted(self._dir.glob("*.md")):
                if path.name.startswith(("_", ".")) or path.name.lower() == "readme.md":
                    continue
                try:
                    if path.stat().st_size > _MAX_PROFILE_BYTES:
                        continue
                    profile = parse(path.read_text(encoding="utf-8"), path.name)
                    if len(profile.instructions) > _MAX_INSTRUCTIONS:
                        continue
                    profiles[profile.name] = profile
                except (OSError, UnicodeError, ValueError):
                    # A malformed optional profile must never stop JINX.
                    continue
        with self._lock:
            self._profiles = profiles
            # JINX is built in and intentionally has no additional instructions;
            # this preserves today's prompt when it is the selected agent.
            if "jinx" not in self._profiles:
                self._profiles["jinx"] = AgentProfile(
                    name="jinx", title="JINX", description="The default JINX assistant",
                    tools=["existing"], instructions="", file="<built-in>",
                )
            self._sessions = {name: self._sessions.get(name, AgentSession())
                              for name in self._profiles}
            if self._active not in self._profiles:
                self._active = "jinx"

    def names(self) -> list[str]:
        with self._lock:
            return sorted(self._profiles)

    def describe(self) -> list[dict]:
        with self._lock:
            return [{"name": p.name, "title": p.title,
                     "description": p.description, "active": p.name == self._active}
                    for p in sorted(self._profiles.values(), key=lambda x: x.name)]

    def current(self) -> AgentProfile:
        with self._lock:
            return self._profiles[self._active]

    def switch(self, name: str) -> AgentProfile:
        key = str(name or "").strip().lower()
        with self._lock:
            if key not in self._profiles:
                raise ValueError(f"unknown agent '{key}'")
            self._active = key
            return self._profiles[key]

    def reset(self, name: str | None = None) -> str:
        with self._lock:
            key = str(name or self._active).strip().lower()
            if key not in self._profiles:
                raise ValueError(f"unknown agent '{key}'")
            self._sessions[key].reset()
            return key

    def add_turn(self, role: str, text: str, name: str | None = None) -> None:
        with self._lock:
            key = str(name or self._active).strip().lower()
            if key in self._sessions:
                self._sessions[key].add(role, text)

    def history(self, name: str | None = None) -> list[str]:
        with self._lock:
            key = str(name or self._active).strip().lower()
            if key not in self._sessions:
                raise ValueError(f"unknown agent '{key}'")
            return self._sessions[key].snapshot()

    def active_context(self) -> str:
        """Return only the selected profile's bounded instructions."""
        with self._lock:
            profile = self._profiles[self._active]
            if profile.name == "jinx" or not profile.instructions:
                return ""
            return ("[ACTIVE AGENT PROFILE]\n"
                    f"Name: {profile.title}\n"
                    f"Role: {profile.description}\n"
                    "The following is role guidance, not executable code:\n"
                    f"{profile.instructions[:_MAX_INSTRUCTIONS]}\n")

    def debate(self, topic: str, turns: int = 4,
               ask: Callable[[str, list[dict], None], dict] | None = None) -> str:
        """Run a bounded, tool-free exchange and return a compact transcript."""
        topic = str(topic or "").strip()[:_MAX_TEXT]
        if not topic:
            raise ValueError("topic is required")
        turns = max(2, min(int(turns), _MAX_DEBATE_TURNS))
        with self._lock:
            candidates = [p for p in self._profiles.values() if p.name != "jinx"]
            if len(candidates) < 2:
                raise ValueError("at least two non-default agents are required")
            left, right = candidates[:2]
        if ask is None:
            from core.tasks.brain import ask as model_ask
            ask = model_ask
        transcript: list[str] = []
        for index in range(turns):
            profile = left if index % 2 == 0 else right
            prior = "\n".join(transcript[-4:])
            system = (f"You are {profile.title}.\n{profile.description}\n"
                      f"{profile.instructions[:_MAX_INSTRUCTIONS]}\n"
                      "This is a mediated debate. Do not call tools, perform actions, "
                      "or claim to have accessed external data. Answer concisely.")
            prompt = (f"Topic: {topic}\nPrevious statements:\n{prior}\n"
                      "Respond to the topic and the other agent in at most 120 words.")
            result = ask(system, [{"role": "user", "text": prompt}], None)
            text = str((result or {}).get("text") or "").strip()[:2_000]
            if not text:
                break
            transcript.append(f"{profile.title}: {text}")
        return "\n".join(transcript)[:8_000]


_default_manager: AgentManager | None = None
_default_lock = RLock()


def get_manager(root: Path | str | None = None) -> AgentManager:
    global _default_manager
    with _default_lock:
        if _default_manager is None:
            base = Path(root) if root is not None else Path(__file__).resolve().parent.parent
            _default_manager = AgentManager(base / "agents")
        return _default_manager
