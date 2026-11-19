import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from detections import Detection
from tracker import Sort
from kalman import KalmanBoxTracker, convert_bbox_to_z

A = (10., 20., 30., 40.)
B = (100., 120., 130., 150.)

def detection(box=A, name='worker', score=.43, index=0):
    return Detection(tuple(box), 0 if name == 'worker' else 1, name, score, index)

class TrackingTests(unittest.TestCase):
    def test_confirmation_counts_initial_observation(self):
        tracker = Sort(min_hits=5)
        for _ in range(4):
            self.assertEqual(tracker.update_detections([detection()]), [])
        self.assertEqual(len(tracker.update_detections([detection()])), 1)

    def test_scores_follow_match_when_order_changes_and_subset_confirms(self):
        tracker = Sort(min_hits=2)
        tracker.update_detections([detection()])
        out = tracker.update_detections([detection(B, 'cow', .91, 0), detection(index=1)])
        self.assertEqual(len(out), 1)
        self.assertEqual((out[0].class_name, out[0].confidence, out[0].detection_index),
                         ('worker', .43, 1))
        out = tracker.update_detections([detection(B, 'cow', .91, 0), detection(index=1)])
        self.assertEqual({r.class_name:r.confidence for r in out}, {'worker':.43,'cow':.91})

    def test_empty_frames_age_and_expire(self):
        tracker = Sort(min_hits=1, max_age=1)
        first = tracker.update_detections([detection()])[0].track_id
        self.assertEqual(tracker.update_detections([]), [])
        self.assertEqual(len(tracker.trackers), 1)
        tracker.update_detections([])
        self.assertEqual(tracker.trackers, [])
        for _ in range(98):
            tracker.update_detections([])
        self.assertNotEqual(tracker.update_detections([detection()])[0].track_id, first)

    def test_confirmed_track_recovers_without_reconfirmation(self):
        tracker = Sort(min_hits=5, max_age=1)
        for _ in range(5): out = tracker.update_detections([detection()])
        first = out[0].track_id
        tracker.update_detections([])
        self.assertEqual(tracker.update_detections([detection()])[0].track_id, first)

    def test_unconfirmed_track_requires_consecutive_hits(self):
        tracker = Sort(min_hits=3, max_age=1)
        tracker.update_detections([detection()])
        tracker.update_detections([])
        for _ in range(2): self.assertEqual(tracker.update_detections([detection()]), [])
        self.assertEqual(len(tracker.update_detections([detection()])), 1)

    def test_class_and_score_update_together(self):
        tracker = Sort(min_hits=1)
        tracker.update_detections([detection(name='balloon', score=.99)])
        out = tracker.update_detections([detection(name='worker', score=.699)])
        self.assertEqual((out[0].class_name, out[0].confidence), ('worker', .699))

    def test_invalid_boxes_filtered_individually(self):
        tracker = Sort(min_hits=1)
        invalid = [(0,0,0,1),(0,0,1,0),(2,0,1,1),(0,0,float('nan'),1),
                   (0,0,float('inf'),1)]
        out = tracker.update_detections([detection(b) for b in invalid] + [detection()])
        self.assertEqual(len(out), 1)
        with self.assertRaises(ValueError):
            convert_bbox_to_z([200., 0., 240., 0.])

    def test_nonfinite_predictions_do_not_shift_tracker_indices(self):
        tracker = Sort(min_hits=1)
        tracker.update_detections([detection(), detection(B, 'cow', .91)])
        tracker.trackers[0].kf.x[0] = np.inf
        out = tracker.update_detections([detection(B, 'cow', .81)])
        self.assertEqual(len(out), 1)
        self.assertEqual((out[0].track_id, out[0].class_name, out[0].confidence), (2,'cow',.81))

    def test_legacy_empty_shapes_and_input_validation(self):
        tracker = Sort(min_hits=1)
        self.assertEqual(tracker.update([], []).shape, (0,6))
        self.assertEqual(tracker.update([A], ['worker']).shape, (1,6))
        self.assertEqual(tracker.update([], []).shape, (0,6))
        self.assertEqual(tracker.update().shape, (0,6))
        with self.assertRaises(ValueError): tracker.update([A], [])
        with self.assertRaises(ValueError): tracker.update([A], ['worker'], [])

    def test_legacy_imports_share_implementation(self):
        from Sort.tracker import Sort as LegacySort
        from Sort.kalman import KalmanBoxTracker as LegacyKalman
        self.assertIs(LegacySort, Sort)
        self.assertIs(LegacyKalman, KalmanBoxTracker)

if __name__ == '__main__': unittest.main()
