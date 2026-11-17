"""IoU association and temporal voting; an identity belongs to a track."""
from __future__ import annotations

import itertools
import threading
from dataclasses import dataclass, field

import numpy as np


@dataclass(slots=True)
class Observation:
    bbox: tuple[int, int, int, int]
    score: float
    quality: float
    embedding: np.ndarray | None


@dataclass(slots=True)
class Track:
    id: int
    bbox: tuple[int, int, int, int]
    created_at: float
    last_seen: float
    hits: int = 1
    label: str = ""
    person_id: str | None = None
    similarity: float = 0.0
    quality: float = 0.0
    embedding: np.ndarray | None = None
    unknown_id: str | None = None
    votes: dict[str, float] = field(default_factory=dict)
    vote_person_ids: dict[str, str | None] = field(default_factory=dict)
    samples: list[tuple[np.ndarray, float]] = field(default_factory=list)

    def vote(self, label: str, person_id: str | None, score: float) -> None:
        if self.hits % 5 == 0:
            self.votes = {key: value * 0.8 for key, value in self.votes.items()}
        self.votes[label] = self.votes.get(label, 0.0) + max(0.0, float(score))
        self.vote_person_ids[label] = person_id
        winner = max(self.votes, key=self.votes.get)
        self.label = winner
        self.person_id = self.vote_person_ids.get(winner)
        self.similarity = float(score) if winner == label else self.similarity

    def add_sample(self, embedding: np.ndarray, quality: float, *, max_samples: int = 40) -> None:
        self.samples.append((np.asarray(embedding, dtype=np.float32).copy(), float(quality)))
        if len(self.samples) > max_samples:
            self.samples.pop(0)


def intersection_over_union(a, b) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    left, top = max(ax, bx), max(ay, by)
    right, bottom = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    intersection = max(0, right - left) * max(0, bottom - top)
    union = max(0, aw) * max(0, ah) + max(0, bw) * max(0, bh) - intersection
    return intersection / union if union else 0.0


class FaceTracker:
    def __init__(self, *, ttl_seconds: float = 2.5, iou_threshold: float = 0.2) -> None:
        self.ttl_seconds = ttl_seconds
        self.iou_threshold = iou_threshold
        self._next_id = itertools.count(1)
        self._tracks: dict[int, Track] = {}
        self._lock = threading.RLock()

    def update(self, observations: list[Observation], *, now: float) -> list[Track]:
        with self._lock:
            expired = [key for key, track in self._tracks.items()
                       if now - track.last_seen > self.ttl_seconds]
            for key in expired:
                del self._tracks[key]

            candidates = sorted(
                ((intersection_over_union(track.bbox, obs.bbox), track.id, index)
                 for track in self._tracks.values()
                 for index, obs in enumerate(observations)), reverse=True)
            used_tracks: set[int] = set()
            used_observations: set[int] = set()
            assignments = []
            for score, track_id, index in candidates:
                if score < self.iou_threshold:
                    break
                if track_id in used_tracks or index in used_observations:
                    continue
                used_tracks.add(track_id)
                used_observations.add(index)
                assignments.append((track_id, index))

            for track_id, index in assignments:
                track, observation = self._tracks[track_id], observations[index]
                track.bbox = observation.bbox
                track.last_seen = now
                track.hits += 1
                track.quality = observation.quality
                track.embedding = observation.embedding
                if observation.embedding is not None and observation.quality >= 0.45:
                    track.add_sample(observation.embedding, observation.quality)

            for index, observation in enumerate(observations):
                if index in used_observations:
                    continue
                track_id = next(self._next_id)
                track = Track(track_id, observation.bbox, now, now)
                track.quality = observation.quality
                track.embedding = observation.embedding
                if observation.embedding is not None and observation.quality >= 0.45:
                    track.add_sample(observation.embedding, observation.quality)
                self._tracks[track_id] = track
            return list(self._tracks.values())

    def tracks(self) -> list[Track]:
        with self._lock:
            return list(self._tracks.values())

    def get(self, track_id: int) -> Track | None:
        with self._lock:
            return self._tracks.get(int(track_id))

    def clear(self) -> None:
        with self._lock:
            self._tracks.clear()
