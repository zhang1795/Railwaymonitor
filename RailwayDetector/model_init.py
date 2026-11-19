"""Lazy, serialized YOLO inference shared by video tasks."""
import os
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import torch

from detections import Detection
from inference_gate import FairInferenceGate

_MODEL_GATE = FairInferenceGate()


class DetectionCancelled(InterruptedError):
    pass


class Detector:
    def __init__(self, weights=None, device=None, model=None, imgsz=640,
                 conf_thres=.25, iou_thres=.3):
        self.weights = weights or os.getenv('RAILWAY_MODEL_PATH',
                    str(Path(__file__).resolve().parent / 'models' / 'best1030.pt'))
        self.device_name = device or os.getenv('RAILWAY_DEVICE', 'cpu')
        self.model = model
        self.device = torch.device(self.device_name) if model is not None else None
        self.imgsz = imgsz
        self.conf_thres, self.iou_thres = conf_thres, iou_thres
        self._load_lock = threading.Lock()
        self._metrics=threading.local()

    def _ensure_model(self,stop_event=None):
        if self.model is not None:
            return
        while not self._load_lock.acquire(timeout=.05):
            if stop_event is not None and stop_event.is_set():raise DetectionCancelled()
        try:
            if self.model is None:
                from models.experimental import attempt_load
                from utils.general import check_img_size
                from utils.torch_utils import select_device
                self.device = select_device(self.device_name)
                with _MODEL_GATE.hold(stop_event,DetectionCancelled):
                    model = attempt_load(self.weights, map_location=self.device)
                    self.imgsz = check_img_size(self.imgsz, s=model.stride.max())
                    if self.device.type != 'cpu':
                        model.half()
                    self.model = model
        finally:self._load_lock.release()

    def metrics(self):return dict(getattr(self._metrics,'value',{}))

    def detect(self, frame, stop_event=None):
        if frame is None or frame.ndim != 3 or frame.shape[2] != 3 or not frame.size:
            raise ValueError('expected a nonempty BGR image')
        if stop_event is not None and stop_event.is_set():
            raise DetectionCancelled()
        self._ensure_model(stop_event)
        from utils.general import non_max_suppression, scale_coords
        image = letterbox(frame, new_shape=self.imgsz)[0]
        image = np.ascontiguousarray(image[:, :, ::-1].transpose(2, 0, 1))
        tensor = torch.from_numpy(image).to(self.device)
        tensor = tensor.half() if self.device.type != 'cpu' else tensor.float()
        tensor = tensor.unsqueeze(0) / 255.
        with _MODEL_GATE.hold(stop_event,DetectionCancelled) as waited:
            if stop_event is not None and stop_event.is_set():
                raise DetectionCancelled()
            with torch.no_grad():
                started=time.monotonic()
                prediction = self.model(tensor)[0]
            self._metrics.value={'inferenceWaitMs':round(waited*1000,3),'inferenceMs':round((time.monotonic()-started)*1000,3)}
        if stop_event is not None and stop_event.is_set():
            raise DetectionCancelled()
        output = non_max_suppression(prediction, self.conf_thres, self.iou_thres)[0]
        if not len(output):
            return []
        output[:, :4] = scale_coords(tensor.shape[2:], output[:, :4], frame.shape)
        names = self.model.module.names if hasattr(self.model, 'module') else self.model.names
        result = []
        for index, row in enumerate(output.detach().cpu().tolist()):
            x1, y1, x2, y2, confidence, class_value = row
            class_id = int(class_value)
            try:
                name = names[class_id]
            except (KeyError, IndexError):
                continue
            detection = Detection((x1, y1, x2, y2), class_id, name, confidence, index)
            if detection.valid():
                result.append(detection)
        return result


_default = Detector()


def detect(frame, stop_event=None):
    return _default.detect(frame, stop_event)


def predict(frame):
    result = []
    scores = []
    for d in detect(frame):
        x1, y1, x2, y2 = d.bbox
        result.append({'objectDetect': d.class_name, 'score': d.confidence,
                       'location': {'center_x': (x1+x2)/2, 'center_y': (y1+y2)/2,
                                    'width': x2-x1, 'height': y2-y1}})
        scores.append(d.confidence)
    return result, scores


def detect_bounding_box(frame):
    records = detect(frame)
    return [list(d.bbox) for d in records], [d.class_name for d in records]


def process_frame(frame, tracker, detector=None, stop_event=None, observed_at=None):
    if stop_event is not None and stop_event.is_set():
        raise DetectionCancelled()
    records = (detector or _default).detect(frame, stop_event)
    if stop_event is not None and stop_event.is_set():
        raise DetectionCancelled()
    return records, tracker.update_detections(records, timestamp=observed_at)


def letterbox(img, new_shape=(640, 640), color=(114, 114, 114), auto=True, scaleFill=False, scaleup=True):
    # Resize image to a 32-pixel-multiple rectangle https://github.com/ultralytics/yolov3/issues/232
    shape = img.shape[:2]  # current shape [height, width]
    if isinstance(new_shape, int):
        new_shape = (new_shape, new_shape)

    # Scale ratio (new / old)
    r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
    if not scaleup:  # only scale down, do not scale up (for better test mAP)
        r = min(r, 1.0)

    # Compute padding
    ratio = r, r  # width, height ratios
    new_unpad = int(round(shape[1] * r)), int(round(shape[0] * r))
    dw, dh = new_shape[1] - new_unpad[0], new_shape[0] - new_unpad[1]  # wh padding
    if auto:  # minimum rectangle
        dw, dh = np.mod(dw, 32), np.mod(dh, 32)  # wh padding
    elif scaleFill:  # stretch
        dw, dh = 0.0, 0.0
        new_unpad = (new_shape[1], new_shape[0])
        ratio = new_shape[1] / shape[1], new_shape[0] / shape[0]  # width, height ratios

    dw /= 2  # divide padding into 2 sides
    dh /= 2

    if shape[::-1] != new_unpad:  # resize
        img = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)
    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
    img = cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)  # add border
    return img, ratio, (dw, dh)
