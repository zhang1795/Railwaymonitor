import numpy as np
import torch.nn
from filterpy.kalman import KalmanFilter
import torch.functional as F
np.random.seed(0)

# 将 [x1,y1,x2,y2] 形式转化为 [center_x,center_y,s,r] 形式
def convert_bbox_to_z(bbox):

    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    x = bbox[0] + w/2.
    y = bbox[1] + h/2.
    s = w * h
    r = w / float(h)

    return np.array([x, y, s, r]).reshape((4, 1))


# 输入的x是一个7维的状态向量，我们只用前4维的边框信息
# 将 [center_x,center_y,s,r] 形式转化为 [x1,y1,x2,y2] 形式
# s = w * h , r = w / h
def convert_x_to_bbox(x):

    w = np.sqrt(x[2] * x[3])
    h = x[2] / w

    return np.array([x[0]-w/2., x[1]-h/2., x[0]+w/2., x[1]+h/2.]).reshape((1, 4))


class KalmanBoxTracker(object):
    count = 1

    # 利用bounding box初始化Kalman滤波轨迹
    def __init__(self, bbox, cls):

        self.cls = cls
        # 定义恒定速度模型，7个状态变量和4个观测输入
        self.kf = KalmanFilter(dim_x=7, dim_z=4)

        # 状态向量 X = [检测框中心的横坐标，检测框中心的纵坐标，检测框的面积，长宽比，横坐标速度，纵坐标速度，面积速度]
        # SORT假设一个物体在不同帧中检测框的长宽比不变，是个常数，所以速度变化只考虑横坐标、横坐标、检测框面积
        self.kf.F = np.array([[1, 0, 0, 0, 1, 0, 0],
                              [0, 1, 0, 0, 0, 1, 0],
                              [0, 0, 1, 0, 0, 0, 1],
                              [0, 0, 0, 1, 0, 0, 0],
                              [0, 0, 0, 0, 1, 0, 0],
                              [0, 0, 0, 0, 0, 1, 0],
                              [0, 0, 0, 0, 0, 0, 1]])

        self.kf.H = np.array([[1, 0, 0, 0, 0, 0, 0],
                              [0, 1, 0, 0, 0, 0, 0],
                              [0, 0, 1, 0, 0, 0, 0],
                              [0, 0, 0, 1, 0, 0, 0]])

        # R是测量噪声的协方差矩阵，即真实值与测量值差的协方差
        # R = diagonal([1, 1, 10, 10])
        self.kf.R[2:, 2:] *= 10.
        # [[ 1.  0.  0.  0.]
        #  [ 0.  1.  0.  0.]
        #  [ 0.  0. 10.  0.]
        #  [ 0.  0.  0. 10.]]

        # P是先验估计的协方差，对不可观测的初始速度，给予高度不确定性
        # P = diagonal([10，10，10，10，1000，1000，1000])
        self.kf.P[4:, 4:] *= 1000.
        self.kf.P *= 10.
        # [[   10.     0.     0.     0.     0.     0.     0.]
        #  [    0.    10.     0.     0.     0.     0.     0.]
        #  [    0.     0.    10.     0.     0.     0.     0.]
        #  [    0.     0.     0.    10.     0.     0.     0.]
        #  [    0.     0.     0.     0. 10000.     0.     0.]
        #  [    0.     0.     0.     0.     0. 10000.     0.]
        #  [    0.     0.     0.     0.     0.     0. 10000.]]

        # Q是系统状态变换误差的协方差
        # Q = diagonal([1, 1, 1, 1, 0.01, 0.01, 0.0001])
        self.kf.Q[-1, -1] *= 0.01
        self.kf.Q[4:, 4:] *= 0.01
        # [[1.e+00 0.e+00 0.e+00 0.e+00 0.e+00 0.e+00 0.e+00]
        #  [0.e+00 1.e+00 0.e+00 0.e+00 0.e+00 0.e+00 0.e+00]
        #  [0.e+00 0.e+00 1.e+00 0.e+00 0.e+00 0.e+00 0.e+00]
        #  [0.e+00 0.e+00 0.e+00 1.e+00 0.e+00 0.e+00 0.e+00]
        #  [0.e+00 0.e+00 0.e+00 0.e+00 1.e-02 0.e+00 0.e+00]
        #  [0.e+00 0.e+00 0.e+00 0.e+00 0.e+00 1.e-02 0.e+00]
        #  [0.e+00 0.e+00 0.e+00 0.e+00 0.e+00 0.e+00 1.e-04]]

        # Kalman滤波器初始化时，直接用第一次观测结果赋值状态信息
        self.kf.x[:4] = convert_bbox_to_z(bbox)

        # 自上次未匹配成功，经过的帧数
        self.time_since_update = 0

        # 每次创建新的kalman滤波器时，计数ID都会加1
        self.id = KalmanBoxTracker.count
        KalmanBoxTracker.count += 1

        # 存储历史时刻的Kalman状态
        self.history = []

        # 自上次未匹配成功，连续成功匹配的帧数
        self.hit_streak = 0

    def update(self, bbox):

        # 利用已经观测到的边框信息，更新状态向量，这里直接调用了kalman库函数，没有自己手动实现Kalman迭代公式

        # 重置，每次匹配成功，则会调用update函数，即自上次未匹配成功，经过的帧数变为了0
        self.time_since_update = 0

        # 清空history
        # 如果匹配成功，则会调用update函数，history会被重置清空，后面会调用predict函数，将最新的状态添加入history列表
        self.history = []

        # 表示连续匹配成功的次数加一
        self.hit_streak += 1

        self.kf.update(convert_bbox_to_z(bbox))

    def predict(self):

        # 如果边界框面积+面积变化速度<=0，就将面积变化速度赋值为0
        # 因为下一时刻边框面积数值，就等于边界框面积+面积变化速度，这样处理可以防止出现面积小于0的情况
        if (self.kf.x[6]+self.kf.x[2]) <= 0:
            self.kf.x[6] *= 0.0

        self.kf.predict()

        # 一旦出现未成功匹配，则连续匹配上的帧数被置0
        if self.time_since_update > 0:
            self.hit_streak = 0

        # 每经过一帧，都会执行predict函数，time_since_update都会加1
        # 但每一帧只有成功匹配上时，才会执行update函数，time_since_update又会被置0
        # 所以time_since_update表示，自上次未成功匹配，所经过的帧数
        self.time_since_update += 1

        # 将当前Kalman状态存入history历史信息列表
        self.history.append(convert_x_to_bbox(self.kf.x))

        return self.history[-1]

    def get_state(self):

        # 返回当前边界框估计值
        return convert_x_to_bbox(self.kf.x)







