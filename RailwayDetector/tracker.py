"""SORT association with frame-local attributes and explicit confirmation."""
import numpy as np
import math
import time
from scipy.optimize import linear_sum_assignment
from detections import Detection, TrackResult
from kalman import KalmanBoxTracker, valid_bbox

def linear_assignment(cost_matrix):
    rows, cols = linear_sum_assignment(cost_matrix)
    return np.column_stack((rows, cols)).astype(int)

def iou_batch(det_box, track_box2):
    a = np.asarray(det_box, dtype=float).reshape(-1, 4)
    b = np.asarray(track_box2, dtype=float)
    b = np.empty((0, 4)) if not b.size else b[:, :4]
    inter = np.maximum(0, np.minimum(a[:, None, 2:], b[None, :, 2:])
                       - np.maximum(a[:, None, :2], b[None, :, :2])).prod(2)
    areas_a = (a[:, 2:] - a[:, :2]).prod(1)
    areas_b = (b[:, 2:] - b[:, :2]).prod(1)
    union = areas_a[:, None] + areas_b[None, :] - inter
    return np.divide(inter, union, out=np.zeros_like(inter), where=union > 0)

def associate_detections_to_trackers(detections, trackers, iou_threshold=.3):
    if not len(detections) or not len(trackers):
        return np.empty((0, 2), dtype=int), np.arange(len(detections)), np.arange(len(trackers))
    iou = iou_batch(detections, trackers)
    admissible = iou >= iou_threshold
    if admissible.sum(1).max() == 1 and admissible.sum(0).max() == 1:
        pairs = np.column_stack(np.where(admissible))
    else:
        pairs = linear_assignment(-iou)
    matched = np.array([p for p in pairs if iou[p[0], p[1]] >= iou_threshold], dtype=int).reshape(-1, 2)
    return (matched, np.setdiff1d(np.arange(len(detections)), matched[:, 0]),
            np.setdiff1d(np.arange(len(trackers)), matched[:, 1]))

class Sort:
    def __init__(self, max_age=1, min_hits=3, iou_threshold=.3, max_idle_seconds=None):
        if max_age < 0 or min_hits < 1 or not 0 <= iou_threshold <= 1:
            raise ValueError('invalid SORT configuration')
        self.max_age, self.min_hits, self.iou_threshold = max_age, min_hits, iou_threshold
        self.trackers = []
        self._next_id = 1
        self.max_idle_seconds = max_idle_seconds
        self._timestamp = None
        if max_idle_seconds is not None and (not math.isfinite(max_idle_seconds) or max_idle_seconds<=0):
            raise ValueError('invalid time-based tracking window')

    def update_detections(self, detections, timestamp=None):
        stamp = time.monotonic() if timestamp is None else float(timestamp)
        if not math.isfinite(stamp) or (self._timestamp is not None and stamp<self._timestamp):
            raise ValueError('tracking clock regressed')
        dt = 1. if self.max_idle_seconds is None or self._timestamp is None else max(.001,stamp-self._timestamp)
        self._timestamp = stamp
        detections = [d for d in detections if d.valid()]
        alive, predictions = [], []
        for track in self.trackers:
            if self.max_idle_seconds is not None and stamp-track.last_match_at>self.max_idle_seconds:
                continue
            pos = track.predict(dt)[0]
            if valid_bbox(pos):
                alive.append(track)
                predictions.append(pos)
        self.trackers = alive
        boxes = np.array([d.bbox for d in detections], dtype=float).reshape(-1, 4)
        predicted = np.array(predictions, dtype=float).reshape(-1, 4)
        matched, unmatched, _ = associate_detections_to_trackers(boxes, predicted, self.iou_threshold)
        for di, ti in matched:
            detection = detections[di]
            track = self.trackers[ti]
            track.update(detection.bbox, detection.class_name)
            track.detection = detection
            track.last_match_at = stamp
        for index in unmatched:
            detection = detections[index]
            track = KalmanBoxTracker(detection.bbox, detection.class_name, self._next_id)
            self._next_id += 1
            track.detection = detection
            track.last_match_at = stamp
            self.trackers.append(track)
        results, survivors = [], []
        for track in self.trackers:
            if self.max_idle_seconds is None and track.time_since_update > self.max_age:
                continue
            box = track.get_state()[0]
            if not valid_bbox(box):
                continue
            survivors.append(track)
            track.confirmed = track.confirmed or track.hit_streak >= self.min_hits
            if track.time_since_update == 0 and track.confirmed:
                d = track.detection
                results.append(TrackResult(tuple(float(x) for x in box), track.id,
                                           d.class_id, d.class_name, d.confidence, d.detection_index))
        self.trackers = survivors
        return results

    def update(self, dets=None, cls=None, scores=None):
        """Legacy rows: xyxy, id, class name, including empty shape (0,6)."""
        boxes = np.asarray([] if dets is None else dets, dtype=float)
        if boxes.size == 0:
            boxes = np.empty((0, 4))
        if boxes.ndim != 2 or boxes.shape[1] not in (4, 5):
            raise ValueError('detections must have shape (N,4) or (N,5)')
        classes = [] if cls is None else list(cls)
        if len(classes) != len(boxes):
            raise ValueError('box/class lengths differ')
        if scores is None:
            scores = boxes[:, 4] if boxes.shape[1] == 5 else np.ones(len(boxes))
        if len(scores) != len(boxes):
            raise ValueError('box/score lengths differ')
        records = [Detection(tuple(b[:4]), -1, str(c), float(s), i)
                   for i, (b, c, s) in enumerate(zip(boxes, classes, scores))]
        results = self.update_detections(records)
        return np.array([list(d.bbox) + [d.track_id, d.class_name] for d in results],
                        dtype=object).reshape(-1, 6)
