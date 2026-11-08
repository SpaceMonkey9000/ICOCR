"""Bounded source-to-current geometry projection for asynchronous overlays.

Display only: never feeds moved boxes back into OCR or its inference cache.
"""
import weakref
import cv2
import numpy as np
from frame_guard import signature, stationary


class FrameCache:
    """Per-frame derived images (signature, small grey, features), kept for a
    few recent frame objects. The overlay worker compares each frame with the
    previous one, so every frame's thumbnail was computed twice; anchors keep
    re-using the same source frame, whose features were recomputed each time.
    Entries are keyed by frame identity (weak references, never by id alone).
    """

    def __init__(self, size=6):
        self.size = size
        self.entries = []

    def get(self, frame):
        for ref, data in self.entries:
            if ref() is frame:
                return data
        data = {}
        self.entries = [e for e in self.entries if e[0]() is not None][-(self.size-1):]
        self.entries.append((weakref.ref(frame), data))
        return data


def _derived(cache, frame, key, compute):
    if cache is None:
        return compute()
    data = cache.get(frame)
    if key not in data:
        data[key] = compute()
    return data[key]


def transform(source, current, cache=None):
    if source is None or current is None or source.shape != current.shape:
        return None
    identity = np.eye(2, 3, dtype=np.float64)
    if source is current or stationary(_derived(cache, source, 'signature', lambda: signature(source)),
                                       _derived(cache, current, 'signature', lambda: signature(current))):
        return identity
    h, w = source.shape[:2]
    factor = min(1., 320/max(h, w))
    size = (max(1, round(w*factor)), max(1, round(h*factor)))
    a, b = [_derived(cache, f, ('grey', size), lambda f=f: cv2.cvtColor(
                cv2.resize(f, size, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY))
            for f in (source, current)]
    points = _derived(cache, source, ('features', size), lambda: cv2.goodFeaturesToTrack(
        a, maxCorners=80, qualityLevel=.015, minDistance=6))
    if points is None or len(points) < 8:
        return None
    opts = dict(winSize=(21,21), maxLevel=2,
                criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 15, .03))
    nxt, ok, _ = cv2.calcOpticalFlowPyrLK(a, b, points, None, **opts)
    if nxt is None:
        return None
    back, reverse, _ = cv2.calcOpticalFlowPyrLK(b, a, nxt, None, **opts)
    if back is None:
        return None
    good = (ok.ravel() > 0) & (reverse.ravel() > 0)
    good &= np.linalg.norm((back-points).reshape(-1,2), axis=1) < 1.
    if good.sum() < 8 or good.mean() < .5:
        return None
    matrix, inliers = cv2.estimateAffinePartial2D(points[good], nxt[good],
        method=cv2.RANSAC, ransacReprojThreshold=1.5, maxIters=100, confidence=.99)
    if matrix is None or not np.isfinite(matrix).all() or inliers.mean() < .75:
        return None
    scale = np.hypot(matrix[0,0], matrix[1,0])
    angle = abs(np.degrees(np.arctan2(matrix[1,0], matrix[0,0])))
    if not .85 <= scale <= 1.18 or angle > 20:
        return None
    if np.linalg.norm(matrix[:,2]/np.array(size)) > .3:
        return None
    # Reject unrelated scenes/occlusions even if a few features happen to match.
    warped = cv2.warpAffine(a, matrix, size)
    mask = cv2.warpAffine(np.ones_like(a), matrix, size, flags=cv2.INTER_NEAREST) > 0
    if mask.mean() < .65 or np.abs(warped.astype(float)-b)[mask].mean() > 18:
        return None
    # Undo resize on both coordinate axes, including rounding of small images.
    resize = np.diag([size[0]/w, size[1]/h, 1.])
    affine = np.vstack([matrix, [0.,0.,1.]])
    return (np.linalg.inv(resize) @ affine @ resize)[:2]


def move_points(points, matrix):
    return (np.asarray(points, dtype=float) @ matrix[:,:2].T + matrix[:,2]).tolist()


def move_row(row, matrix):
    moved = dict(row, box=move_points(row['box'], matrix))
    if row.get('body_box') is not None:
        moved['body_box'] = move_points(row['body_box'], matrix)
    return moved


def move_detection(found, matrix):
    x1,y1,x2,y2 = found['box']
    polygon = move_points(found.get('polygon') or [[x1,y1],[x2,y1],[x2,y2],[x1,y2]], matrix)
    pts = np.asarray(polygon)
    moved = dict(found, polygon=polygon, box=[*pts.min(axis=0), *pts.max(axis=0)])
    if found.get('mask_polygon'):
        # 0.8.4.3: a segmentation outline moves with its quad.
        moved['mask_polygon'] = move_points(found['mask_polygon'], matrix)
    return moved
