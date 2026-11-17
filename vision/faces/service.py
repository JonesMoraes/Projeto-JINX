"""Local face identity service, connected to JINX's in-process event bus."""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from core.events import EventBus
from vision.faces.engine import (DEFAULT_THRESHOLD, LEARNING_QUALITY_MIN,
                                 MATCH_QUALITY_MIN, calibrated_threshold,
                                 match_embedding, quality_score,
                                 select_diverse_samples)
from vision.faces.store import FaceStore
from vision.faces.tracker import FaceTracker, Observation, Track

_BUS = EventBus()
_SERVICE = None
_SERVICE_LOCK = threading.RLock()


class FaceService:
    """Frames are processed in memory; persistent data contains embeddings only."""

    def __init__(self, *, store: FaceStore | None = None, backend=None,
                 event_bus: EventBus | None = None, clock=time.monotonic) -> None:
        self.store = store or FaceStore()
        self.backend = backend
        self.events = event_bus or _BUS
        self.clock = clock
        self._lock = threading.RLock()
        self._active = False
        self._trackers: dict[str, FaceTracker] = defaultdict(FaceTracker)
        self._frame_counts: dict[str, int] = defaultdict(int)
        self._last_sighting: dict[tuple[str, int], float] = {}
        self._last_person_seen: dict[str, float] = {}
        self._adaptive_at: dict[str, float] = {}
        self._prompted_unknowns: dict[str, float] = {}
        self._conflicts: dict[tuple[str, str], float] = {}
        self._last_results: dict[str, list[dict]] = defaultdict(list)
        self._threshold = DEFAULT_THRESHOLD

    @property
    def active(self) -> bool:
        with self._lock:
            return self._active

    @property
    def threshold(self) -> float:
        return self._threshold

    def start(self, *, backend_name: str = "opencv_sface", provider: str = "cpu",
              download_models: bool = True) -> str:
        from vision.faces.backends.opencv import create_backend

        with self._lock:
            if self._active:
                return "Face identity is already active."
            backend = self.backend
        if backend is None:
            backend = create_backend(backend_name, provider=provider,
                                     download=download_models)
        with self._lock:
            if self.backend is not None and self.backend.name != backend.name:
                stored = self.store.exemplars(backend=self.backend.name, dim=self.backend.dimension)
                if stored:
                    raise RuntimeError("Changing face backend requires a full re-enrollment campaign")
            self.backend = backend
            exemplars = self.store.exemplars(backend=backend.name, dim=backend.dimension)
            self._threshold = calibrated_threshold(exemplars, base=backend.threshold)
            self._active = True
            self.store.expire_unknowns(days=30)
        return f"Face identity active with {backend.name}; threshold={self._threshold:.3f}."

    def stop(self) -> None:
        with self._lock:
            self._active = False
            self._trackers.clear()
            self._frame_counts.clear()
            self._last_sighting.clear()
            self._last_results.clear()

    def status(self) -> dict:
        with self._lock:
            return {"active": self._active,
                    "backend": getattr(self.backend, "name", None),
                    "threshold": round(self._threshold, 4),
                    "people": len(self.store.list_people()),
                    "unknown_clusters": len(self.store.list_unknowns()),
                    "storage": "SQLite embeddings only; raw frames are not retained"}

    def feed(self, frame, *, camera: str = "webcam") -> list[dict]:
        with self._lock:
            if not self._active or self.backend is None:
                return []
            self._frame_counts[camera] += 1
            frame_count = self._frame_counts[camera]
            tracker = self._trackers[camera]
            backend = self.backend
        now = self.clock()
        self._emit_departures(now, camera)
        if frame_count % 3:
            tracker.update([], now=now)
            return list(self._last_results[camera])

        observations = []
        try:
            for detection in backend.detect(frame):
                quality = quality_score(frame, detection.bbox, detection.score)
                embedding = None
                if quality >= MATCH_QUALITY_MIN:
                    embedding = backend.embed(frame, detection)
                observations.append(Observation(detection.bbox, detection.score, quality, embedding))
        except Exception:
            return list(self._last_results[camera])

        tracks = tracker.update(observations, now=now)
        current = [track for track in tracks if track.last_seen == now]
        results = []
        for track in current:
            if track.embedding is None or track.quality < MATCH_QUALITY_MIN:
                results.append(self._result(track, camera, track.label or "unknown",
                                            track.similarity if track.person_id else None))
                continue
            positives = self.store.exemplars(backend=backend.name, dim=backend.dimension, negative=False)
            negatives = self.store.exemplars(backend=backend.name, dim=backend.dimension, negative=True)
            prior_person = track.person_id
            offset = self.store.threshold_offset(prior_person) if prior_person else 0.0
            match = match_embedding(track.embedding, positives, negatives,
                                    threshold=self._threshold + offset)
            if match:
                person = self.store.get_person(match["person_id"])
                if person and person["consent"]:
                    track.vote(person["name"], person["id"], match["similarity"])
                    track.unknown_id = None
                    self._record_person(track, person, camera, now)
                    self._adaptive_learn(track, person, backend, now)
                    self._check_conflicts(person, backend)
                    result = self._result(track, camera, person["name"], match["similarity"])
                    results.append(result)
                    self.events.publish("face", label=person["name"], person_id=person["id"],
                                        camera=camera, track_id=track.id,
                                        similarity=match["similarity"])
                    self._presence(person, camera, now)
                    continue
            unknowns = self.store.unknown_vectors(backend=backend.name, dim=backend.dimension)
            unknown_scores = [(float(np.dot(track.embedding, row["embedding"])), row["id"])
                              for row in unknowns]
            unknown_threshold = self._threshold + 0.05
            if unknown_scores and max(unknown_scores)[0] >= unknown_threshold:
                _score, unknown_id = max(unknown_scores)
                cluster_id, _count = self.store.add_unknown(
                    track.embedding, backend=backend.name, threshold=unknown_threshold)
                track.unknown_id = cluster_id or unknown_id
            else:
                track.unknown_id, _count = self.store.add_unknown(
                    track.embedding, backend=backend.name, threshold=unknown_threshold)
            track.vote("unknown", None, 0.5)
            self._record_unknown(track, camera, now)
            result = self._result(track, camera, track.label or "unknown",
                                  track.similarity if track.person_id else None)
            results.append(result)
            self._prompt_unknown(track, camera, now)
            self.events.publish("face", label="unknown", person_id=None, camera=camera,
                                track_id=track.id, similarity=None)
        self._last_results[camera] = results
        return results

    def _record_person(self, track: Track, person: dict, camera: str, now: float) -> None:
        key = (camera, track.id)
        if now - self._last_sighting.get(key, -1e9) >= 5.0:
            self.store.record_sighting(person_id=person["id"], unknown_id=None,
                                       label=person["name"], camera=camera,
                                       track_id=str(track.id), similarity=track.similarity)
            self._last_sighting[key] = now

    def _record_unknown(self, track: Track, camera: str, now: float) -> None:
        key = (camera, track.id)
        if now - self._last_sighting.get(key, -1e9) >= 5.0:
            self.store.record_sighting(person_id=None, unknown_id=track.unknown_id,
                                       label="unknown", camera=camera,
                                       track_id=str(track.id))
            self._last_sighting[key] = now

    def _presence(self, person: dict, camera: str, now: float) -> None:
        previous = self._last_person_seen.get(person["id"])
        if previous is None or now - previous > 300:
            self.events.publish("presence", person=person["name"], person_id=person["id"],
                                event="arrived", camera=camera)
        self._last_person_seen[person["id"]] = now

    def _prompt_unknown(self, track: Track, camera: str, now: float) -> None:
        if not track.unknown_id:
            return
        previous = self._prompted_unknowns.get(track.unknown_id, -1e9)
        if now - previous >= 86400:
            self._prompted_unknowns[track.unknown_id] = now
            self.events.publish("unknown_person", unknown_id=track.unknown_id,
                                camera=camera, track_id=track.id)

    def _adaptive_learn(self, track: Track, person: dict, backend, now: float) -> None:
        if (track.quality < LEARNING_QUALITY_MIN or track.hits < 20 or
                track.similarity < self._threshold + 0.18 or
                now - self._adaptive_at.get(person["id"], -1e9) < 120):
            return
        self.store.add_exemplar(person["id"], track.embedding, backend=backend.name,
                                quality=track.quality, source="adaptive", anchor=False)
        self.store.prune_adaptive(person["id"])
        self._adaptive_at[person["id"]] = now

    def _check_conflicts(self, person: dict, backend) -> None:
        exemplars = self.store.exemplars(backend=backend.name, dim=backend.dimension, negative=False)
        vectors: dict[str, list[np.ndarray]] = defaultdict(list)
        for row in exemplars:
            vectors[row["person_id"]].append(row["embedding"])
        own = vectors.get(person["id"], [])
        if not own:
            return
        own_centroid = np.mean(own, axis=0)
        for other_id, other_vectors in vectors.items():
            if other_id == person["id"] or not other_vectors:
                continue
            score = float(np.dot(own_centroid / max(np.linalg.norm(own_centroid), 1e-8),
                                 np.mean(other_vectors, axis=0) /
                                 max(np.linalg.norm(np.mean(other_vectors, axis=0)), 1e-8)))
            if score >= self._threshold:
                other = self.store.get_person(other_id)
                pair = tuple(sorted((person["id"], other_id)))
                now = self.clock()
                if now - self._conflicts.get(pair, -1e9) >= 3600:
                    self._conflicts[pair] = now
                    self.events.publish("identity_conflict", person_id=person["id"],
                                        person=person["name"], other_person_id=other_id,
                                        other_person=other["name"] if other else "",
                                        similarity=score)

    def _emit_departures(self, now: float, camera: str) -> None:
        departed = [person_id for person_id, last_seen in self._last_person_seen.items()
                    if now - last_seen > 300]
        for person_id in departed:
            person = self.store.get_person(person_id)
            self._last_person_seen.pop(person_id, None)
            if person:
                self.events.publish("presence", person=person["name"], person_id=person_id,
                                    event="left", camera=camera)

    @staticmethod
    def _result(track: Track, camera: str, label: str, similarity: float | None) -> dict:
        return {"track_id": track.id, "camera": camera, "label": label,
                "person_id": track.person_id, "similarity": similarity,
                "bbox": tuple(int(value) for value in track.bbox),
                "quality": round(track.quality, 3), "hits": track.hits}

    def enroll_photo(self, image_path: str | Path, name: str) -> dict:
        return self.enroll_photos([image_path], name, minimum_samples=1)

    def enroll_photos(self, image_paths, name: str, *, minimum_samples: int = 1,
                      profile: dict | None = None) -> dict:
        if self.backend is None:
            self.start()
        import cv2

        candidates = []
        for image_path in image_paths:
            image = cv2.imread(str(Path(image_path).expanduser()), cv2.IMREAD_COLOR)
            if image is None:
                continue
            faces = self.backend.detect(image)
            faces = sorted(faces, key=lambda item: item.bbox[2] * item.bbox[3], reverse=True)
            for detection in faces[:3]:
                quality = quality_score(image, detection.bbox, detection.score)
                if quality >= LEARNING_QUALITY_MIN:
                    candidates.append((quality, self.backend.embed(image, detection)))
                    break
        if len(candidates) < minimum_samples:
            raise ValueError(f"Need {minimum_samples} clear face samples; got {len(candidates)}")
        if minimum_samples >= 3 or len(candidates) > 1:
            samples = select_diverse_samples(candidates, count=12,
                                            minimum=max(1, minimum_samples))
        else:
            samples = [max(candidates, key=lambda item: item[0])]
        if not samples:
            raise ValueError("No face passed the enrollment quality threshold")
        person = self.store.create_person(name, consent=True, profile=profile)
        for quality, embedding in samples:
            self.store.add_exemplar(person["id"], embedding, backend=self.backend.name,
                                    quality=quality, source="photo", anchor=True)
        self._recalibrate()
        return self.store.get_person(person["id"])

    def enroll_live(self, name: str, *, camera: str = "webcam") -> dict:
        if not self.active:
            raise RuntimeError("Start local face identity before live enrollment")
        tracks = [track for track in self._trackers[camera].tracks() if track.hits >= 3]
        if not tracks:
            raise ValueError("No stable face track is available; look at the camera")
        track = max(tracks, key=lambda candidate: (candidate.hits, candidate.last_seen))
        samples = select_diverse_samples(track.samples, count=12, minimum=3)
        person = self.store.create_person(name, consent=True)
        for embedding, quality in samples:
            self.store.add_exemplar(person["id"], embedding, backend=self.backend.name,
                                    quality=quality, source="live-voice", anchor=True)
        track.label, track.person_id, track.unknown_id = person["name"], person["id"], None
        self._recalibrate()
        return self.store.get_person(person["id"])

    def name_unknown(self, unknown_id: str, name: str) -> dict:
        person = self.store.promote_unknown(unknown_id, name)
        self._recalibrate()
        for tracker in self._trackers.values():
            for track in tracker.tracks():
                if track.unknown_id == unknown_id:
                    track.label, track.person_id, track.unknown_id = person["name"], person["id"], None
        return self.store.get_person(person["id"])

    def forget(self, name_or_id: str) -> bool:
        person = self.store.find_person(name_or_id) or self.store.get_person(name_or_id)
        if not person:
            return False
        removed = self.store.delete_person(person["id"])
        self._recalibrate()
        return removed

    def correct(self, track_id: int, correct_name: str, *, camera: str = "webcam") -> None:
        track = self._trackers[camera].get(track_id)
        person = self.store.find_person(correct_name)
        if track is None or track.embedding is None or person is None:
            raise ValueError("Stable track and existing person are required")
        self.store.correct_identity(track_id=str(track.id), claimed=track.label or "unknown",
                                    correct=person["name"], person_id=person["id"],
                                    embedding=track.embedding, backend=self.backend.name,
                                    quality=max(track.quality, MATCH_QUALITY_MIN))
        track.label, track.person_id, track.unknown_id = person["name"], person["id"], None
        self._recalibrate()

    def _recalibrate(self) -> None:
        if self.backend is None:
            return
        rows = self.store.exemplars(backend=self.backend.name, dim=self.backend.dimension, negative=False)
        self._threshold = calibrated_threshold(rows, base=self.backend.threshold)


def get_service() -> FaceService:
    global _SERVICE
    with _SERVICE_LOCK:
        if _SERVICE is None:
            _SERVICE = FaceService()
        return _SERVICE
