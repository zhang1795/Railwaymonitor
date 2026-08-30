import time
import os

import numpy as np
import cv2
import torch
from numpy import random

from models.experimental import attempt_load
from utils.general import check_img_size, non_max_suppression, scale_coords, \
    set_logging
from utils.torch_utils import select_device, time_synchronized
from utils.plots import Annotator, colors
from sort import *
mot_tracker = Sort(max_age=1, min_hits=3, iou_threshold=0.3)


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


#weights = r'./models/roaddetection.pt'
#weights = r'./models/military.pt'
weights = os.getenv('RAILWAY_MODEL_PATH', './models/best1030.pt')
opt_device = os.getenv('RAILWAY_DEVICE', 'cpu')  # 初步部署默认使用 CPU
imgsz = 640
opt_conf_thres = 0.25
opt_iou_thres = 0.3
# Initialize
set_logging()
device = select_device(opt_device)
half = device.type != 'cpu'  # half precision only supported on CUDA
# Load model
model = attempt_load(weights, map_location=device) # load FP32 model
imgsz = check_img_size(imgsz, s=model.stride.max())  # check img_size
if half:
    model.half()  # to FP16
# Get names and colors
names = model.module.names if hasattr(model, 'module') else model.names
# colors = [[random.randint(0, 255) for _ in range(3)] for _ in names1]

# from utils.plots import plot_one_box,plot_one_box_PIL

def plot_one_box(x, img, label=None, color=None, line_thickness=3):
    c1, c2 = (int(x[0]), int(x[1])), (int(x[2]), int(x[3]))
    tl = line_thickness or round(0.002 * (img.shape[0] + img.shape[1]) / 2) + 1  # line/font thickness
    color = color or [random.randint(0, 255) for _ in range(3)]
    cv2.rectangle(img, c1, c2, color, thickness=tl, lineType=cv2.LINE_AA)
    if label:
        tf = max(tl - 1, 1)  # font thickness
        t_size = cv2.getTextSize(label, 0, fontScale=tl / 3, thickness=tf)[0]
        c2 = c1[0] + t_size[0], c1[1] - t_size[1] - 3
        cv2.rectangle(img, c1, c2, color, -1, cv2.LINE_AA)  # filled
        cv2.putText(img, label, (c1[0], c1[1] - 2), 0, tl / 3, [225, 255, 255], thickness=tf, lineType=cv2.LINE_AA)


def predict(im0s):
    # Run inference
    img = torch.zeros((1, 3, imgsz, imgsz), device=device)  # init img
    # _ = predict_model(img.half() if half else img) if device.type != 'cpu' else None  # run once
    # Set Dataloader & Run inference
    img = letterbox(im0s, new_shape=imgsz)[0]
    # Convert
    img = img[:, :, ::-1].transpose(2, 0, 1)  # BGR to RGB, to 3x416x416
    img = np.ascontiguousarray(img)

    img = torch.from_numpy(img).to(device)
    img = img.half() if half else img.float()  # uint8 to fp16/32
    img /= 255.0  # 0 - 255 to 0.0 - 1.0
    if img.ndimension() == 3:
        img = img.unsqueeze(0)
    # Inference
    #pred = model(img, augment=opt.augment)[0]
    pred = model(img)[0]
    # Apply NMS
    pred = non_max_suppression(pred, opt_conf_thres, opt_iou_thres)
    # Process detections
    ret = []
    score = []
    for i, det in enumerate(pred):  # detections per image
        if len(det):
            # Rescale boxes from img_size to im0 size
            det[:, :4] = scale_coords(img.shape[2:], det[:, :4], im0s.shape).round()
            # Write results
            for *xyxy, conf, cls in reversed(det):
                label = f'{names[int(cls)]} {conf:.2f}'
                label2 = f'{names[int(cls)]}'
                prob = round(float(conf),2)  # round 2
                #plot_one_box(xyxy, im0s, label=label, color=colors(int(cls)), line_thickness=3)
                xywh = xyxy
                x = int(xywh[0])
                y = int(xywh[1])
                w = x+(int(xywh[2]) - int(xywh[0]))/2
                h = y+(int(xywh[3]) - int(xywh[1]))/2
                w1 = (int(xywh[2]) - int(xywh[0]))
                h1 = (int(xywh[3]) - int(xywh[1]))
                position = {'center_x': w, 'center_y': h, 'width': w1, 'height': h1}
                ret_i = {'objectDetect': label2, 'score': prob, 'location': position}
                ret.append(ret_i)
                score.append(prob)
    return ret,score

def detect_bounding_box(im0s):

    boxes = []
    classes = []
    img = torch.zeros((1, 3, imgsz, imgsz), device=device)  # init img
    # _ = predict_model(img.half() if half else img) if device.type != 'cpu' else None  # run once
    # Set Dataloader & Run inference
    img = letterbox(im0s, new_shape=imgsz)[0]
    # Convert
    img = img[:, :, ::-1].transpose(2, 0, 1)  # BGR to RGB, to 3x416x416
    img = np.ascontiguousarray(img)

    img = torch.from_numpy(img).to(device)
    img = img.half() if half else img.float()  # uint8 to fp16/32
    img /= 255.0  # 0 - 255 to 0.0 - 1.0
    if img.ndimension() == 3:
        img = img.unsqueeze(0)
    # Inference
    # pred = model(img, augment=opt.augment)[0]
    pred = model(img)[0]
    # Apply NMS
    pred = non_max_suppression(pred, opt_conf_thres, opt_iou_thres)
    for i, det in enumerate(pred):

        if len(det):
                # 将预测的尺寸从imgs回到原图片尺寸
            det[:, :4] = scale_coords(img.shape[2:], det[:, :4], im0s.shape).round()
            for *xyxy, conf, cls in reversed(det):
                box = []
                for value in xyxy:
                    box.append(float(value))
                c = int(cls)
                classes.append(names[c])
                boxes.append(box)
        # boxes包含结果（x1,y1,x2,y2）
    return boxes, classes
