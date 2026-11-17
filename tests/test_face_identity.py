import tempfile
import unittest
from pathlib import Path

import numpy as np

from core.events import EventBus
from vision.faces.engine import (calibrated_threshold, cosine_similarity,
                                 match_embedding, quality_score,
                                 select_diverse_samples)
from vision.faces.service import FaceService
from vision.faces.store import FaceStore
from vision.faces.tracker import FaceTracker, Observation


def unit(index, size=8):
    result = np.zeros(size, dtype=np.float32)
    result[index] = 1
    return result


class FaceEngineTests(unittest.TestCase):
    def test_diversity_picker_rejects_duplicate_samples(self):
        vectors = [(unit(0), .9), (unit(0), .95), (unit(1), .8), (unit(2), .7)]
        selected = select_diverse_samples(vectors, count=3, minimum=3)
        self.assertEqual(len(selected), 3)
        with self.assertRaises(ValueError):
            select_diverse_samples(vectors[:2], minimum=2)

    def test_matching_uses_top_three_mean_and_negative_exemplar(self):
        positives = [
            {"person_id": "a", "embedding": unit(0)},
            {"person_id": "a", "embedding": unit(0)},
            {"person_id": "a", "embedding": unit(1)},
            {"person_id": "a", "embedding": unit(2)},
            {"person_id": "b", "embedding": unit(3)},
        ]
        found = match_embedding(unit(0), positives, [], threshold=.3)
        self.assertEqual(found["person_id"], "a")
        rejected = match_embedding(unit(0), positives,
                                   [{"person_id": "a", "embedding": unit(0)}], threshold=.3)
        self.assertIsNone(rejected)

    def test_threshold_uses_impostors_and_stays_bounded(self):
        rows = [{"person_id": "a", "embedding": unit(0)},
                {"person_id": "b", "embedding": unit(1)}]
        threshold = calibrated_threshold(rows, base=.363)
        self.assertGreaterEqual(threshold, .183)
        self.assertLessEqual(threshold, .543)
        self.assertEqual(calibrated_threshold(rows[:1], base=.363), .363)
        self.assertAlmostEqual(cosine_similarity(unit(0), unit(0)), 1.0)

    def test_quality_gate_scores_clear_detailed_face_higher(self):
        import cv2
        rng = np.random.default_rng(4)
        clear = rng.integers(20, 235, size=(140, 140, 3), dtype=np.uint8)
        blurry = np.zeros((24, 24, 3), dtype=np.uint8)
        self.assertGreater(quality_score(clear, (0, 0, 140, 140), .95), .6)
        self.assertLess(quality_score(blurry, (0, 0, 24, 24), .95), .45)


class FaceStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = FaceStore(Path(self.temp.name) / "faces.db")

    def test_backend_dimensions_cannot_be_mixed_for_one_person(self):
        person = self.store.create_person("Maria")
        self.store.add_exemplar(person["id"], unit(0), backend="sface", quality=.9)
        with self.assertRaises(ValueError):
            self.store.add_exemplar(person["id"], unit(0, 16), backend="other", quality=.9)

    def test_unknown_promotion_relabels_past_sightings_and_delete_cascades(self):
        unknown_id, _ = self.store.add_unknown(unit(0), backend="sface", threshold=.4)
        self.store.record_sighting(person_id=None, unknown_id=unknown_id, label="unknown",
                                   camera="front", track_id="17")
        person = self.store.promote_unknown(unknown_id, "Maria")
        self.assertEqual(self.store.sightings_for_unknown(unknown_id), 0)
        rows = self.store.sightings_for_person(person["id"])
        self.assertEqual(rows[0]["label"], "Maria")
        self.assertTrue(self.store.delete_person(person["id"]))
        self.assertEqual(self.store.list_people(), [])

    def test_adaptive_pruning_keeps_every_anchor(self):
        person = self.store.create_person("Jones")
        for index in range(3):
            self.store.add_exemplar(person["id"], unit(index), backend="sface",
                                    quality=.8, anchor=True)
        for index in range(3, 8):
            self.store.add_exemplar(person["id"], unit(index), backend="sface",
                                    quality=.1 + index / 100, anchor=False)
        self.assertEqual(self.store.prune_adaptive(person["id"], cap=5), 3)
        rows = self.store.exemplars(backend="sface", dim=8, negative=False)
        anchors = [row for row in rows if row["anchor"]]
        self.assertEqual(len(anchors), 3)
        self.assertEqual(len(rows), 5)

    def test_unknown_clusters_merge_and_expire(self):
        first, _ = self.store.add_unknown(unit(0), backend="sface", threshold=.4)
        second, _ = self.store.add_unknown(unit(1), backend="sface", threshold=.4)
        self.assertTrue(self.store.merge_unknowns(first, second))
        self.assertEqual(len(self.store.list_unknowns()), 1)
        self.assertEqual(self.store.list_unknowns()[0]["n"], 2)


class FaceTrackerTests(unittest.TestCase):
    def test_iou_association_preserves_track_and_ttl_expires(self):
        tracker = FaceTracker(ttl_seconds=2.5)
        first = tracker.update([Observation((0, 0, 20, 20), .9, .8, unit(0))], now=1.0)[0]
        second = tracker.update([Observation((1, 1, 20, 20), .9, .8, unit(0))], now=2.0)[0]
        self.assertEqual(first.id, second.id)
        self.assertEqual(second.hits, 2)
        self.assertEqual(tracker.update([], now=5.0), [])


class FaceServiceTests(unittest.TestCase):
    def test_verified_local_match_emits_face_and_presence_events(self):
        class FakeBackend:
            name = "fake"
            dimension = 8
            threshold = .36

            def detect(self, _frame):
                from vision.faces.base import FaceDetection
                return [FaceDetection((0, 0, 140, 140), .99)]

            def embed(self, _frame, _detection):
                return unit(0)

        bus = EventBus()
        events = []
        bus.subscribe("*", events.append)
        with tempfile.TemporaryDirectory() as folder:
            store = FaceStore(Path(folder) / "faces.db")
            person = store.create_person("Maria")
            store.add_exemplar(person["id"], unit(0), backend="fake", quality=.9)
            service = FaceService(store=store, backend=FakeBackend(), event_bus=bus,
                                  clock=lambda: 10.0)
            service.start()
            frame = np.random.default_rng(5).integers(20, 235, size=(140, 140, 3), dtype=np.uint8)
            service.feed(frame, camera="front")
            service.feed(frame, camera="front")
            result = service.feed(frame, camera="front")
            self.assertEqual(result[0]["label"], "Maria")
            self.assertTrue(any(event.name == "presence" for event in events))
            self.assertTrue(any(event.name == "face" for event in events))
            service.stop()


if __name__ == "__main__":
    unittest.main()
