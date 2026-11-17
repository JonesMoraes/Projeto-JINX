"""Common types and protocol for pluggable face-recognition backends."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np


@dataclass(frozen=True, slots=True)
class FaceDetection:
    bbox: tuple[int, int, int, int]
    score: float
    landmarks: tuple[float, ...] = ()
    raw: tuple[float, ...] = ()


@runtime_checkable
class FaceBackend(Protocol):
    name: str
    dimension: int
    threshold: float

    def detect(self, frame: np.ndarray) -> list[FaceDetection]: ...
    def embed(self, frame: np.ndarray, detection: FaceDetection) -> np.ndarray: ...


def normalize_embedding(value, *, expected_dim: int | None = None) -> np.ndarray:
    """Validate and L2-normalize one finite embedding into float32."""
    vector = np.asarray(value, dtype=np.float32).reshape(-1)
    if expected_dim is not None and vector.size != expected_dim:
        raise ValueError(f"embedding dimension {vector.size} != expected {expected_dim}")
    if vector.size == 0 or not np.isfinite(vector).all():
        raise ValueError("embedding must contain finite values")
    norm = float(np.linalg.norm(vector))
    if norm <= 1e-8:
        raise ValueError("embedding norm is zero")
    return vector / norm


def default_model_directory() -> Path:
    """The cache is outside the project so models never enter Git by accident."""
    return Path.home() / ".jinx" / "models" / "faces"
