"""Pure face quality, embedding selection, matching and calibration routines."""
from __future__ import annotations

from collections import defaultdict

import numpy as np

from vision.faces.base import normalize_embedding

DEFAULT_THRESHOLD = 0.363
MATCH_QUALITY_MIN = 0.45
LEARNING_QUALITY_MIN = 0.60
MAX_PERSON_EXEMPLARS = 60


def cosine_similarity(left, right) -> float:
    a = normalize_embedding(left)
    b = normalize_embedding(right, expected_dim=a.size)
    return float(np.clip(np.dot(a, b), -1.0, 1.0))


def quality_score(frame, bbox, detection_score: float) -> float:
    """Weighted 0..1 gate from face size, Laplacian sharpness, light, detector."""
    import cv2

    height, width = frame.shape[:2]
    x, y, box_w, box_h = (int(v) for v in bbox)
    left, top = max(0, x), max(0, y)
    right, bottom = min(width, x + box_w), min(height, y + box_h)
    if right <= left or bottom <= top:
        return 0.0
    crop = frame[top:bottom, left:right]
    if crop.size == 0:
        return 0.0
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    face_size = min(1.0, float(np.sqrt(crop.shape[0] * crop.shape[1])) / 120.0)
    sharpness = min(1.0, float(cv2.Laplacian(gray, cv2.CV_64F).var()) / 180.0)
    brightness = float(np.mean(gray))
    exposure = max(0.0, 1.0 - abs(brightness - 127.5) / 127.5)
    detection = float(np.clip(detection_score, 0.0, 1.0))
    return float(np.clip(0.30 * face_size + 0.25 * sharpness +
                         0.20 * exposure + 0.25 * detection, 0.0, 1.0))


def select_diverse_samples(samples, *, count: int = 12, minimum: int = 3,
                           max_pair_similarity: float = 0.93) -> list[tuple[np.ndarray, float]]:
    """Greedily choose quality-ranked samples whose pairwise cosine is diverse."""
    valid = [(normalize_embedding(vector), float(quality)) for vector, quality in samples
             if float(quality) >= LEARNING_QUALITY_MIN]
    valid.sort(key=lambda item: item[1], reverse=True)
    chosen: list[tuple[np.ndarray, float]] = []
    for vector, quality in valid:
        if all(cosine_similarity(vector, other) < max_pair_similarity
               for other, _ in chosen):
            chosen.append((vector, quality))
            if len(chosen) >= count:
                break
    if len(chosen) < minimum:
        raise ValueError(f"Need at least {minimum} diverse, quality samples; got {len(chosen)}")
    return chosen


def match_embedding(query, exemplars: list[dict], negatives: list[dict], *,
                    threshold: float) -> dict | None:
    """Top-three mean cosine per person, rejected by a stronger negative vector."""
    query_vector = normalize_embedding(query)
    scores: dict[str, list[float]] = defaultdict(list)
    for exemplar in exemplars:
        if exemplar.get("negative") or exemplar["embedding"].size != query_vector.size:
            continue
        scores[str(exemplar["person_id"])].append(
            cosine_similarity(query_vector, exemplar["embedding"]))
    if not scores:
        return None
    person_scores = {person_id: float(np.mean(sorted(values, reverse=True)[:3]))
                     for person_id, values in scores.items()}
    person_id, similarity = max(person_scores.items(), key=lambda item: item[1])
    impostor = max((cosine_similarity(query_vector, item["embedding"])
                    for item in negatives if item.get("person_id") == person_id), default=-1.0)
    if similarity < threshold or impostor >= similarity:
        return None
    return {"person_id": person_id, "similarity": similarity,
            "negative_similarity": impostor}


def calibrated_threshold(exemplars: list[dict], *, base: float = DEFAULT_THRESHOLD) -> float:
    """Calibrate from inter-person centroid similarities, bounded around base."""
    by_person: dict[str, list[np.ndarray]] = defaultdict(list)
    for row in exemplars:
        if row.get("negative"):
            continue
        by_person[str(row["person_id"])].append(normalize_embedding(row["embedding"]))
    centroids = []
    for vectors in by_person.values():
        centroids.append(normalize_embedding(np.mean(vectors, axis=0)))
    impostors = [cosine_similarity(left, right)
                 for index, left in enumerate(centroids)
                 for right in centroids[index + 1:]]
    if not impostors:
        return float(base)
    derived = float(np.percentile(np.asarray(impostors), 99.5)) + 0.03
    return float(np.clip(derived, base - 0.18, base + 0.18))
