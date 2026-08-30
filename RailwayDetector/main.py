from yolov5.my_yolo import YOLO
from Sort.tracker import Sort
from yolov5.utils.datasets import LoadImages
from yolov5.utils.general import check_img_size, check_requirements, increment_path
import numpy as np
import argparse
import os
import cv2 as cv

def parse_opt():
    parser = argparse.ArgumentParser()
    parser.add_argument('--save', default=True, help='save results')
    parser.add_argument('--save_txt', default=False, help='save txt results')
    parser.add_argument('--save_dir', default='yolov5_outputs/runs', help='save results dir')
    parser.add_argument('--show', default=True, help='show frame img')

    opt = parser.parse_args()
    return opt

def main():
    opt = parse_opt()
    colours = np.random.rand(32, 3) * 255
    yolo = YOLO()
    mot_tracker = Sort(max_age=1, min_hits=5, iou_threshold=0.3)
    # 检测图像长宽所用
    imgsz = check_img_size(yolo.imgsz, s=yolo.model.stride)  # check image size
    dataset = LoadImages(path='./yolov5/data/images', img_size=imgsz, stride=yolo.stride, auto=yolo.model.pt)
    vid_path, vid_writer = [None] * 1, [None] * 1
    if opt.save:
        # Directories
        save_dir = increment_path(opt.save_dir)  # increment run
        (save_dir / 'labels' if opt.save_txt else save_dir).mkdir(parents=True, exist_ok=True)  # make dir

    for path, im, im0s, vid_cap, s in dataset:
        # 从YOLOV5中获得当前帧的检测结果
        detect_boxes, detect_classes = yolo.detect_bounding_box(im, im0s)
        # 将检测结果放入跟踪器中，获得融合结果
        tracker = mot_tracker.update(detect_boxes, detect_classes)
        for d in tracker:
            x1 = int(float(d[0]))
            y1 = int(float(d[1]))
            x2 = int(float(d[2]))
            y2 = int(float(d[3]))
            pred_id = str(int(d[4]))
            rgb = colours[int(d[4]) % 32]
            pred_cls = d[5]
            text = pred_id + ':' + pred_cls
            cv.rectangle(im0s, (x1, y1), (x2, y2), rgb, 2, 1)
            cv.putText(im0s, text, (int((x1 + x2) / 2), int((y1 + y2) / 2)), 2, 1, (0, 255, 0))


        # 每一帧一展示，方便调试
        if opt.show:
            cv.namedWindow('detect_img')
            cv.imshow('img', im0s)
            cv.waitKey()

        # Save results (image with detections)
        if opt.save:
            image_name = path[path.rfind('\\') + 1:]
            save_path = os.path.join(save_dir, image_name)
            if dataset.mode == 'image':
                cv.imwrite(save_path, im0s)
            else:
                if vid_path[0] != save_path:  # new video
                    vid_path[0] = save_path
                    if isinstance(vid_writer[0], cv.VideoWriter):
                        vid_writer[0].release()  # release previous video writer
                    if vid_cap:  # video
                        fps = vid_cap.get(cv.CAP_PROP_FPS)
                        w = int(vid_cap.get(cv.CAP_PROP_FRAME_WIDTH))
                        h = int(vid_cap.get(cv.CAP_PROP_FRAME_HEIGHT))
                    vid_writer[0] = cv.VideoWriter(save_path, cv.VideoWriter_fourcc(*'mp4v'), fps, (w, h))
                vid_writer[0].write(im0s)


if __name__ == '__main__':
    check_requirements()
    main()
