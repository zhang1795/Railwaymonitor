"""SORT constant-velocity Kalman state, with validated geometry."""
import threading
import numpy as np
from filterpy.kalman import KalmanFilter

def valid_bbox(bbox):
    b = np.asarray(bbox, dtype=float)
    return b.shape == (4,) and np.isfinite(b).all() and b[2] > b[0] and b[3] > b[1]

def convert_bbox_to_z(bbox):
    if not valid_bbox(bbox):
        raise ValueError('bounding box must have finite coordinates and positive width/height')
    x1, y1, x2, y2 = np.asarray(bbox, dtype=float)
    w, h = x2 - x1, y2 - y1
    return np.array([(x1+x2)/2, (y1+y2)/2, w*h, w/h]).reshape(4, 1)

def convert_x_to_bbox(x):
    x = np.asarray(x).reshape(-1)
    if not np.isfinite(x).all() or x[2] <= 0 or x[3] <= 0:
        return np.full((1, 4), np.nan)
    w = np.sqrt(x[2] * x[3])
    h = x[2] / w
    return np.array([x[0]-w/2, x[1]-h/2, x[0]+w/2, x[1]+h/2]).reshape(1, 4)

class KalmanBoxTracker:
    count = 1
    _id_lock = threading.Lock()

    def __init__(self, bbox, cls, track_id=None):
        measurement = convert_bbox_to_z(bbox)
        self.cls = cls
        self.kf = KalmanFilter(dim_x=7, dim_z=4)
        self.kf.F = np.eye(7)
        self.kf.F[0, 4] = self.kf.F[1, 5] = self.kf.F[2, 6] = 1
        self.kf.H = np.eye(4, 7)
        self.kf.R[2:, 2:] *= 10.
        self.kf.P[4:, 4:] *= 1000.
        self.kf.P *= 10.
        self.kf.Q[-1, -1] *= .01
        self.kf.Q[4:, 4:] *= .01
        self.kf.x[:4] = measurement
        if track_id is None:
            with self._id_lock:
                track_id = KalmanBoxTracker.count
                KalmanBoxTracker.count += 1
        self.id = track_id
        self.time_since_update = 0
        self.hit_streak = 1
        self.confirmed = False
        self.detection = None
        self.history = []

    def update(self, bbox, cls=None):
        self.kf.update(convert_bbox_to_z(bbox))
        self.time_since_update = 0
        self.history = []
        self.hit_streak += 1
        if cls is not None:
            self.cls = cls

    def predict(self, dt=1.):
        if not np.isfinite(self.kf.x).all():
            return np.full((1, 4), np.nan)
        if (self.kf.x[6] + self.kf.x[2]) <= 0:
            self.kf.x[6] = 0
        self.kf.F[0,4] = self.kf.F[1,5] = self.kf.F[2,6] = dt
        self.kf.predict()
        if self.time_since_update > 0:
            self.hit_streak = 0
        self.time_since_update += 1
        self.history = [convert_x_to_bbox(self.kf.x)]
        return self.history[-1]

    def get_state(self):
        return convert_x_to_bbox(self.kf.x)
