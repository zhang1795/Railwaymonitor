"""Isolated audit probes against current code, not acceptance tests or benchmarks.

No model weights, network, cameras or business database are used.
Run from the repository root with the existing detector Python environment.
"""
import contextlib
import io
import json
from pathlib import Path
from queue import Queue
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'RailwayDetector'), str(ROOT / 'RailwayDetector/tests')]
import ui
from detections import Detection
from tracker import Sort
from test_worker import Capture, Writer, message


class ContinuousDetector:
    def __init__(self, fail_at=None):
        self.calls = 0
        self.fail_at = fail_at

    def detect(self, frame, stop):
        self.calls += 1
        if self.calls == self.fail_at:
            raise RuntimeError('audit injected inference failure')
        return [Detection((5., 5., 25., 25.), 12, 'worker', .8, 0)]


def worker_probe(frames, fail_at=None):
    queues, writers, delivered, before_eof = [], [], [], []

    class ObservedQueue(Queue):
        def __init__(self):
            super().__init__()
            self.peak = 0
            queues.append(self)

        def put(self, item, *args, **kwargs):
            super().put(item, *args, **kwargs)
            self.peak = max(self.peak, self.qsize())

    class Source(Capture):
        def read(self):
            if self.index == self.frames:
                before_eof.append(len(delivered))
            return super().read()

    def writer(*args):
        value = Writer(*args)
        writers.append(value)
        return value

    source = Source(frames=frames)
    error = None
    with tempfile.TemporaryDirectory() as folder, patch.object(ui, 'Queue', ObservedQueue):
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                ui.make_result(message(), detector=ContinuousDetector(fail_at),
                               capture_factory=lambda _: source, writer_factory=writer,
                               publish=delivered.append, output_dir=folder)
            except RuntimeError as exc:
                error = str(exc)
    return dict(input_frames=frames, published_before_eof=before_eof,
                published_total=len(delivered), pending_queue_peak=queues[1].peak,
                pending_queue_maxsize=queues[1].maxsize, error=error,
                resources_released=source.releases == 1 and all(w.releases == 1 for w in writers))


def tracking_probe():
    tracker = Sort(max_age=1, min_hits=5, iou_threshold=.3)
    worker = Detection((10., 10., 100., 100.), 12, 'worker', .8, 0)
    for _ in range(5):
        initial = tracker.update_detections([worker])
    # A supported, different class with identical geometry is associated to the
    # existing ID. This demonstrates missing semantic gating, not bird accuracy.
    changed = tracker.update_detections([
        Detection(worker.bbox, 6, 'kite', .99, 0)])
    tracker.update_detections([])
    tracker.update_detections([])
    remaining = len(tracker.trackers)
    for _ in range(5):
        reappeared = tracker.update_detections([worker])
    return dict(initial_id=initial[0].track_id,
                interfering_class_id=changed[0].track_id,
                interfering_class=changed[0].class_name,
                tracks_after_two_misses=remaining,
                reappeared_id=reappeared[0].track_id)


if __name__ == '__main__':
    report = {'continuous_target': worker_probe(300),
              'failure_with_pending_results': worker_probe(30, fail_at=11),
              'tracking': tracking_probe()}
    assert report['continuous_target']['published_before_eof'] == [0]
    assert report['continuous_target']['pending_queue_peak'] == 300
    assert report['continuous_target']['published_total'] == 296
    assert report['failure_with_pending_results']['published_total'] == 0
    assert report['tracking']['initial_id'] == report['tracking']['interfering_class_id']
    assert report['tracking']['reappeared_id'] != report['tracking']['initial_id']
    print(json.dumps(report, ensure_ascii=False, indent=2))
