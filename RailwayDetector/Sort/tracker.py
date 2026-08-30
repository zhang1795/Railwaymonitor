import numpy as np
import torch

from yolov5.utils.metrics import box_iou
from scipy.optimize import linear_sum_assignment
from kalman import KalmanBoxTracker
np.random.seed(0)


# 匈牙利匹配
def linear_assignment(cost_matrix):
    x, y = linear_sum_assignment(cost_matrix)
    return np.array(list(zip(x, y)))


# 用于计算det中的目标框和卡尔曼滤波追踪的目标框的iou
def iou_batch(det_box, track_box2):
    # 将list转为numpy格式
    det_box = np.array(det_box)
    track_box2 = np.array(track_box2)
    # 再将numpy转为tensor，速度更快
    det_box = torch.from_numpy(det_box)
    # 注意这里box2
    track_box2 = torch.from_numpy(track_box2[:, 0:4])
    # 调库算iou
    iou = box_iou(det_box, track_box2)
    return np.array(iou)


def associate_detections_to_trackers(detections, trackers, iou_threshold=0.3):

    # 初始化时，trackers为空，直接返回空匹配结果
    if len(trackers) == 0:
        return np.empty((0, 2), dtype=int), np.arange(len(detections)), np.empty((0, 5), dtype=int)

    # 这里trackers多一列ID列
    iou_matrix = iou_batch(detections, trackers)
    # [[0.73691421 0.         0.         0.        ]
    #  [0.         0.89356082 0.         0.        ]
    #  [0.         0.         0.76781823 0.        ]]

    if min(iou_matrix.shape) > 0:

        a = (iou_matrix > iou_threshold).astype(np.int32)
        # [[1 0 0 0]
        #  [0 1 0 0]
        #  [0 0 1 0]]

        # print(a.sum(1)): [1 1 1]
        # print(a.sum(0)): [1 1 1 0]
        # a.sum(1)表示将矩阵所有列累加，a.sum(0)表示将矩阵所有行累加

        # 如果大于0.3的位置恰好一一对应，可直接得到匹配结果，否则利用匈牙利算法进行匹配
        if a.sum(1).max() == 1 and a.sum(0).max() == 1:

            matched_indices = np.stack(np.where(a), axis=1)
            # [[0 0]
            #  [1 1]
            #  [2 2]]
        else:
            matched_indices = linear_assignment(-iou_matrix)
    else:
        matched_indices = np.empty(shape=(0, 2))

    unmatched_detections = []
    for d, det in enumerate(detections):
        if d not in matched_indices[:, 0]:
            unmatched_detections.append(d)

    unmatched_trackers = []
    for t, trk in enumerate(trackers):
        if t not in matched_indices[:, 1]:
            unmatched_trackers.append(t)

    # print(unmatched_detections) : []
    # print(unmatched_trackers) : [3]

    # 匈牙利算法匹配出的结果，未必符合IOU大于0.3，需要再进行一次筛选
    # 如果匹配后的IOU数值依旧很小，则同样默认为未匹配成功
    matches = []
    for m in matched_indices:
        if iou_matrix[m[0], m[1]] < iou_threshold:
            unmatched_detections.append(m[0])
            unmatched_trackers.append(m[1])
        else:
            matches.append(m.reshape(1, 2))

    if len(matches) == 0:
        matches = np.empty((0, 2), dtype=int)
    else:
        matches = np.concatenate(matches, axis=0)

    # print(matches): [[0 0] [1 1] [2 2]]
    # print(np.array(unmatched_detections)): []
    # print(np.array(unmatched_trackers)): [3]

    return matches, np.array(unmatched_detections), np.array(unmatched_trackers)


class Sort(object):

    def __init__(self, max_age=1, min_hits=3, iou_threshold=0.3):

        self.max_age = max_age    # 1
        self.min_hits = min_hits    # 3
        self.iou_threshold = iou_threshold    # 0.3

        # trackers列表中存储的每一个元素，都是一个特定目标物体的Kalman滤波过程
        self.trackers = []

    def update(self, dets=np.empty((0, 4)), cls=np.empty(0)):

        # det_s是当前帧目标检测结果，默认初始值为np.empty((0, 5))，代表当前帧没有检测到任何目标物体
        # trk_s存储Kalman滤波器对当前帧的位置预测结果

        trks = np.zeros((len(self.trackers), 5))
        to_del = []

        # ret是最终返回值，存储当前帧的目标跟踪结果
        ret = []

        # 类似c++中的引用，每次trk_s中的trk值被修改，trk_s整个数组也会被修改
        for t, trk in enumerate(trks):

            # 对每个轨迹调用Kalman滤波predict函数，预测当前帧的位置
            pos = self.trackers[t].predict()[0]
            # [286.552 154.138 357.889 321.466]

            trk[:] = [pos[0], pos[1], pos[2], pos[3], 1]

            # np.isnan()是判断是否是空值
            # np.any，或的关系，只要有一个满足，则输出为TRUE
            if np.any(np.isnan(pos)):
                to_del.append(t)

        # np.ma.masked_invalid函数：当数组a中某些元素为无效值(NaNs or inf)时，则将无效值的元素设置为mask(–)
        # np.ma.compress_rows函数：返回被屏蔽完成以后的数组
        trks = np.ma.compress_rows(np.ma.masked_invalid(trks))
        for t in reversed(to_del):
            self.trackers.pop(t)

        # 将Kalman滤波器预测出来的位置，与当前检测出的位置，进行匹配
        matched, unmatched_dets, unmatched_trks = associate_detections_to_trackers(dets, trks, self.iou_threshold)

        # 如果匹配成功，则用观测信息进一步更新Kalman滤波器状态
        for m in matched:
            self.trackers[m[1]].update(dets[m[0]])

        # 对于未匹配上的检测结果，默认为出现新轨迹，初始化创建新的Kalman滤波器
        for i in unmatched_dets:
            trk = KalmanBoxTracker(dets[i], cls[i])
            self.trackers.append(trk)

        # 对当前tracks列表中的Kalman滤波器依次检验，销毁无效的轨迹，返回当前帧的目标跟踪结果
        i = len(self.trackers)
        for trk in reversed(self.trackers):

            # 以逆序方式，从倒数第一个开始遍历tracks列表中的Kalman滤波器
            d = trk.get_state()[0]

            # trk.time_since_update<1表示，该轨迹状态自上次未被匹配到，经过的帧数小于1，也就是当前帧成功匹配
            # trk.hit_streak>=表示，自上次未被匹配到，连续匹配的帧数大于等于3
            if (trk.time_since_update < 1) and (trk.hit_streak > self.min_hits):
                ret.append(np.concatenate((d, [trk.id], [trk.cls])).reshape(1, -1))

            i -= 1

            # 如果连续未被匹配到大于等于2帧，删除销毁无效的轨迹
            if trk.time_since_update > self.max_age:
                self.trackers.pop(i)

        if len(ret) > 0:

            # 返回的是，当前帧被认为真正有效的轨迹坐标、对应ID
            # [[542.825 206.921 566.939 251.902   4.   ]
            #  [456.542 213.434 481.675 270.969   3.   ]
            #  [222.571 179.989 256.338 288.916   2.   ]
            #  [286.552 154.138 357.889 321.466   1.   ]]

            return np.concatenate(ret)

        return np.empty((0, 5))


