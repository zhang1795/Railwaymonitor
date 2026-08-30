from yolov5.utils.general import non_max_suppression, scale_coords
from yolov5.models.common import DetectMultiBackend
from yolov5.utils.torch_utils import select_device
import torch
from pathlib import Path
import sys
import os

FILE = Path(__file__).resolve()
ROOT = FILE.parents[0]  # YOLOv5 root directory
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))  # add ROOT to PATH
ROOT = Path(os.path.relpath(ROOT, Path.cwd()))  # relative


class YOLO(object):
    _defaults = {
        'weights': ROOT / 'best.pt',
        'data': ROOT / 'data/my_yolo.yaml',  # dataset.yaml path
        'imgsz': (640, 640),
        'device': '',
        'augment': False,
        'conf_thres': 0.5,  # 置信度阈值
        'iou_thres': 0.45,  # IOU检测阈值
        'classes': None,  # 模型忽略某些类型
        'max_det': 1000,  # maximum detections per image
        'agnostic_nms': False,  # NMS时是否去除同类别的框
    }

    @classmethod
    def get_defaults(cls, n):
        if n in cls._defaults:
            return cls._defaults[n]
        else:
            return "Unrecognized attribute name '" + n + "'"

    def __init__(self, **kwargs):
        self.__dict__.update(self._defaults)
        for name, value in kwargs.items():
            setattr(self, name, value)

        # 选择运行硬件
        self.device = select_device(self.device)
        # 载入模型
        self.model = DetectMultiBackend(self.weights, device=self.device, data=self.data)
        # names是dataset上类别的名字 stride是模型最大下采样步数
        self.stride, self.names, self.pt = self.model.stride, self.model.names, self.model.pt
        # 预热模型，在预测前，将一个空的tensor放进模型预测测试
        self.model.warmup(imgsz=(1, 3, *self.imgsz))

    def detect_bounding_box(self, im, im0s):

        boxes = []
        classes = []
        # 将图片转为tensor格式
        im = torch.from_numpy(im).to(self.device)
        # 转为float型
        im = im.float()
        # 归一化
        im /= 255  # 0 - 255 to 0.0 - 1.0
        # 如果维度不够3维，补成3维
        if len(im.shape) == 3:
            im = im[None]  # expand for batch dim
        # 预测
        pred = self.model(im, augment=self.augment)
        # 对结果NMS
        pred = non_max_suppression(pred, self.conf_thres, self.iou_thres, self.classes, self.agnostic_nms,
                                   max_det=self.max_det)

        for i, det in enumerate(pred):

            if len(det):
                # 将预测的尺寸从imgs回到原图片尺寸
                det[:, :4] = scale_coords(im.shape[2:], det[:, :4], im0s.shape).round()
                for *xyxy, conf, cls in reversed(det):
                    box = []
                    for value in xyxy:
                        box.append(float(value))
                    c = int(cls)
                    classes.append(self.names[c])
                    boxes.append(box)

        # boxes包含结果（x1,y1,x2,y2）
        return boxes, classes
