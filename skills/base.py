"""Contracts shared by dynamically loaded skills."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class SkillResult:
    """Structured skill outcome, suitable for logs and model tool results."""

    status: str
    message: str = ""
    data: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in {"done", "unverified", "failed"}:
            raise ValueError("status must be done, unverified, or failed")


@dataclass(frozen=True, slots=True)
class SkillContext:
    """Capabilities provided to a skill without exposing application globals."""

    os_backend: Any = None
    event_bus: Any = None
    services: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


class BaseSkill(ABC):
    """Base class for handlers declared by a skill's ``handler.py``."""

    @abstractmethod
    async def run(self, params: dict[str, Any], ctx: SkillContext) -> SkillResult:
        """Execute the skill and return a structured result."""
