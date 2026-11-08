"""Sparse optical flow with forward/backward, affine and appearance checks.
All public boxes are full-resolution frame coordinates. No OCR is run here.
"""
from config_loader import tuning
import cv2
import numpy as np


def tracking_gray(frame):
    """Optical-flow working image (grey, at most tracking.max_width wide).
    The tracking worker computes it once per frame for every tracker."""
    h, w = frame.shape[:2]
    size = (min(w, tuning('tracking.max_width')), max(1, round(h * min(1., tuning('tracking.max_width')/w))))
    small = cv2.resize(frame, size, interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)


class ICTracker:
    def __init__(self):
        self.reset()

    def reset(self):
        self.row = None
        self.previous = None
        self.points = None
        self.matrix = np.eye(3)
        self.frame_shape = None

    @property
    def active(self):
        return self.row is not None

    def gray(self, frame):
        return tracking_gray(frame)

    def features(self, gray, box):
        mask = np.zeros_like(gray)
        cv2.fillConvexPoly(mask, np.round(box).astype(np.int32), 255)
        mask = cv2.dilate(mask, np.ones((17, 17), np.uint8))
        return cv2.goodFeaturesToTrack(gray, 100, tuning('ic_tracker.feature_quality'), 3, mask=mask, blockSize=5)

    def start(self, frame, row, gray=None):
        """gray: optional precomputed tracking_gray(frame)."""
        self.reset()
        gray = self.gray(frame) if gray is None else gray
        h,w = frame.shape[:2]
        self.ratio = np.array([gray.shape[1]/w, gray.shape[0]/h])
        box = np.asarray(row['box'], dtype=np.float32) * self.ratio
        points = self.features(gray, box)
        if points is None or len(points) < 8:
            return False
        lo = np.maximum(np.floor(box.min(axis=0)-6).astype(int), 0)
        hi = np.minimum(np.ceil(box.max(axis=0)+6).astype(int), gray.shape[::-1])
        x,y = lo; right,bottom = hi
        template = gray[y:bottom, x:right].copy()
        if min(template.shape) < 8 or float(template.std()) < 5:
            return False
        self.template = template
        self.origin = lo
        self.initial_box = box
        self.initial_body = (np.asarray(row['body_box'],np.float32)*self.ratio
                             if row.get('body_box') is not None else None)
        self.current_box = box
        self.row = dict(row)
        self.previous = gray
        self.points = points
        self.frame_shape = frame.shape[:2]
        return True

    def update(self, frame, gray=None):
        """gray: optional precomputed tracking_gray(frame)."""
        if not self.active:
            return False
        if frame.shape[:2] != self.frame_shape:
            self.reset(); return False
        gray = self.gray(frame) if gray is None else gray
        options = dict(winSize=(25,25), maxLevel=3,
                       criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 25, tuning('ic_tracker.optical_flow_epsilon')))
        nxt, status, _ = cv2.calcOpticalFlowPyrLK(self.previous, gray, self.points, None, **options)
        if nxt is None:
            self.reset(); return False
        back, back_status, _ = cv2.calcOpticalFlowPyrLK(gray, self.previous, nxt, None, **options)
        if back is None:
            self.reset(); return False
        good = (status.ravel() != 0) & (back_status.ravel() != 0)
        good &= np.linalg.norm(back-self.points, axis=2).ravel() < tuning('tracking.forward_backward_error')
        old = self.points[good].reshape(-1,2)
        new = nxt[good].reshape(-1,2)
        if len(old) < 6:
            self.reset(); return False
        affine, inliers = cv2.estimateAffinePartial2D(old, new, method=cv2.RANSAC,
                                                    ransacReprojThreshold=tuning('ic_tracker.ransac_error_pixels'), maxIters=500)
        if affine is None or inliers.sum() < 6 or inliers.mean() < tuning('tracking.minimum_inlier_ratio'):
            self.reset(); return False
        scale = float(np.hypot(affine[0,0], affine[1,0]))
        if not tuning('ic_tracker.scale_min') < scale < tuning('ic_tracker.scale_max'):
            self.reset(); return False
        matrix = np.vstack([affine, [0,0,1]]) @ self.matrix
        box = cv2.transform(self.initial_box[None], matrix[:2])[0]
        h,w = gray.shape
        if np.any(box[:,0] < 2) or np.any(box[:,0] > w-3) or np.any(box[:,1] < 2) or np.any(box[:,1] > h-3):
            self.reset(); return False
        # Compare the aligned marking to the original. This rejects a tracker
        # following nearby PCB texture after the chip has been covered/replaced.
        inverse = np.linalg.inv(matrix)
        inverse[:2,2] -= self.origin
        th,tw = self.template.shape
        aligned = cv2.warpAffine(gray, inverse[:2], (tw,th))
        correlation = float(cv2.matchTemplate(aligned, self.template, cv2.TM_CCOEFF_NORMED)[0,0])
        if not np.isfinite(correlation) or correlation < tuning('tracking.minimum_correlation'):
            self.reset(); return False
        self.matrix = matrix
        self.current_box = box
        self.row = dict(self.row, box=(box/self.ratio).tolist())
        if self.initial_body is not None:
            self.row['body_box'] = (cv2.transform(self.initial_body[None],matrix[:2])[0]/self.ratio).tolist()
        self.previous = gray
        # Retain inliers; replenish on the target when feature count falls.
        points = new[inliers.ravel() != 0].reshape(-1,1,2)
        self.points = self.features(gray, box) if len(points) < 25 else points
        if self.points is None or len(self.points) < 6:
            self.reset(); return False
        return True

    def inside(self, roi, frame_shape):
        if not self.active:
            return False
        h,w = frame_shape[:2]
        centre = np.asarray(self.row['box']).mean(axis=0) / [w,h]
        return roi[0] <= centre[0] <= roi[2] and roi[1] <= centre[1] <= roi[3]
