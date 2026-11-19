import os
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
config = Path(tempfile.gettempdir()) / 'railway-fix-tests'
config.mkdir(exist_ok=True)
os.environ['YOLOV5_CONFIG_DIR'] = str(config / 'yolo')
os.environ['MPLCONFIGDIR'] = str(config / 'matplotlib')
from model_init import Detector, DetectionCancelled, process_frame, _MODEL_GATE
from tracker import Sort

class Model(torch.nn.Module):
    names = ['worker','cow']
    def __init__(self):
        super().__init__()
        self.calls = self.active = self.peak = 0
        self.empty = False
        self.guard = threading.Lock()
    def forward(self, image):
        with self.guard:
            self.calls += 1
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            time.sleep(.01)
            if self.empty:
                return (torch.zeros((1,0,7)),)
            return (torch.tensor([[[40.,40.,10.,10.,.8,.2,.9]]]),)
        finally:
            with self.guard: self.active -= 1

class DetectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(2)
        Detector(model=Model()).detect(np.zeros((640,640,3), np.uint8))

    def test_one_forward_nms_and_update_per_frame_including_empty(self):
        from utils.general import non_max_suppression
        model = Model()
        detector = Detector(model=model)
        tracker = Sort(min_hits=1)
        frame = np.zeros((640,640,3), np.uint8)
        with patch('utils.general.non_max_suppression', wraps=non_max_suppression) as nms:
            for index in range(6):
                model.empty = bool(index % 2)
                records, tracks = process_frame(frame, tracker, detector)
                self.assertEqual(bool(records), not model.empty)
            self.assertEqual(nms.call_count, 6)
        self.assertEqual(model.calls, 6)
        self.assertEqual(tracker.trackers[0].time_since_update, 1)

    def test_scores_keep_precision(self):
        records = Detector(model=Model()).detect(np.zeros((640,640,3), np.uint8))
        self.assertAlmostEqual(records[0].confidence, .72, places=6)
        self.assertEqual(records[0].class_name, 'cow')

    def test_mixed_shapes_are_serialized(self):
        model = Model()
        detector = Detector(model=model)
        shapes = [(360,640),(640,360),(640,640),(720,1280)] * 4
        with ThreadPoolExecutor(max_workers=4) as pool:
            outputs = list(pool.map(lambda size: detector.detect(np.zeros((*size,3),np.uint8)), shapes))
        self.assertEqual(model.calls, len(shapes))
        self.assertEqual(model.peak, 1)
        self.assertEqual(len(outputs), len(shapes))

    def test_waiting_inference_can_be_cancelled(self):
        model = Model()
        detector = Detector(model=model)
        stop = threading.Event()
        errors = []
        def run():
            try: detector.detect(np.zeros((640,640,3),np.uint8), stop)
            except DetectionCancelled: errors.append('cancelled')
        with _MODEL_GATE.hold():
            thread = threading.Thread(target=run)
            thread.start()
            time.sleep(.15)
            stop.set()
            thread.join(2)
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors, ['cancelled'])
        self.assertEqual(model.calls, 0)

    def test_padding_box_is_removed_after_coordinate_restoration(self):
        model = Model()
        with patch.object(model, 'forward', return_value=(torch.tensor([[[110.,5.,20.,10.,.9,.1,.9]]]),)):
            records = Detector(model=model).detect(np.zeros((720,1280,3),np.uint8))
        self.assertEqual(records, [])

if __name__ == '__main__': unittest.main()
