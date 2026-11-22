"""Frame-synchronous, drift-free overlay tracking (display only).

Every preview frame is registered directly against the frame that was scanned,
so the outline drawn on a frame was measured on that same frame: there is no
lag between video and overlay and no drift from chaining frame-to-frame steps.

Method: the scan frame (``reference``) is reduced to a small grey image with
corner features. For each new frame the reference is warped by the previous
solution, so only the small residual motion has to be found by pyramidal
Lucas-Kanade; a similarity transform reference -> current is then fitted with
RANSAC to the original reference points. Large jumps are recovered with phase
correlation. Moved geometry is never fed back into OCR.

Qt-free: numpy and OpenCV only.
"""
import cv2
import numpy as np

MAX_SIDE = 480          # tracking resolution (longest side, pixels)
MAX_FEATURES = 220
MIN_TRACKED = 10
LK = dict(winSize=(21, 21), maxLevel=3,
          criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, .03))
IDENTITY = np.eye(2, 3, dtype=np.float64)


def tracking_size(shape):
    """(width, height) of the tracking image for a frame of ``shape``."""
    h, w = shape[:2]
    factor = min(1., MAX_SIDE/max(h, w, 1))
    return max(1, round(w*factor)), max(1, round(h*factor))


def tracking_gray(frame, size=None):
    """Small grey image used for tracking; computed once per frame."""
    size = size or tracking_size(frame.shape)
    if (frame.shape[1], frame.shape[0]) != size:
        # INTER_AREA averages sensor noise; the source is at most a preview frame
        # or one full frame per scan, so the cost is small.
        frame = cv2.resize(frame, size, interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame


def _apply(matrix, points):
    return points @ matrix[:, :2].T + matrix[:, 2]


class OverlayTracker:
    """Tracks one scanned frame. ``update`` returns a 2x3 full-resolution affine
    (scan-frame pixels -> current-frame pixels) or None while tracking is lost."""

    def __init__(self, reference, frame_shape=None):
        """``reference``: the scanned frame, or a reduced copy of it when
        ``frame_shape`` gives the full-resolution (height, width)."""
        self.shape = tuple((frame_shape or reference.shape)[:2])
        self.size = tracking_size(self.shape)
        self.reference = tracking_gray(reference, self.size)
        points = cv2.goodFeaturesToTrack(self.reference, maxCorners=MAX_FEATURES,
                                         qualityLevel=.01, minDistance=7)
        self.points = (np.empty((0, 2), np.float32) if points is None
                       else points.reshape(-1, 2).astype(np.float32))
        self.usable = len(self.points) >= MIN_TRACKED
        self.matrix = IDENTITY.copy()      # last raw solution, tracking pixels
        self.smooth = None                 # displayed (filtered) solution
        self.lost = 0                      # consecutive frames without a solution
        w, h = self.size
        self._corners = np.array([[0, 0], [w, 0], [w, h], [0, h]], np.float64)
        sx, sy = w/self.shape[1], h/self.shape[0]
        self._down = np.diag([sx, sy, 1.])
        self._up = np.diag([1/sx, 1/sy, 1.])

    # -- public ---------------------------------------------------------------
    def update(self, gray):
        """``gray``: ``tracking_gray(frame, tracker.size)`` of the current frame."""
        if not self.usable or gray.shape != self.reference.shape:
            self.lost += 1
            return None
        solution = self._solve(self.matrix, gray)
        if solution is None:
            solution = self._recover(gray)
        if solution is None:
            self.lost += 1
            self.smooth = None
            return None
        self.matrix = solution
        self.lost = 0
        self.smooth = self._filter(solution)
        return self.full_matrix(self.smooth)

    def full_matrix(self, matrix):
        """Tracking-pixel affine expressed in full-resolution frame pixels."""
        return (self._up @ np.vstack([matrix, [0., 0., 1.]]) @ self._down)[:2]

    # -- internals ------------------------------------------------------------
    def _filter(self, solution):
        """Suppress sub-pixel solver jitter without adding lag to real motion.

        The correction applied to the displayed transform grows with how far
        the outline would move: a still board stays rock steady, anything above
        about half a tracking pixel is followed immediately.
        """
        if self.smooth is None:
            return solution
        move = np.abs(_apply(solution, self._corners) - _apply(self.smooth, self._corners)).max()
        alpha = float(np.clip(move/.6, .25, 1.))
        return self.smooth + alpha*(solution - self.smooth)

    def _recover(self, gray):
        """Large jump between frames: estimate the global shift and retry."""
        w, h = self.size
        for guess in (self.matrix, IDENTITY):
            warped = cv2.warpAffine(self.reference, guess, (w, h), borderMode=cv2.BORDER_REPLICATE)
            (dx, dy), response = cv2.phaseCorrelate(np.float32(warped), np.float32(gray))
            if response < .05 or not np.isfinite([dx, dy]).all():
                continue
            shifted = guess.copy()
            shifted[:, 2] += (dx, dy)
            solution = self._solve(shifted, gray)
            if solution is not None:
                return solution
        return None

    def _solve(self, guess, gray):
        w, h = self.size
        identity = np.array_equal(guess, IDENTITY)
        warped = self.reference if identity else cv2.warpAffine(
            self.reference, guess, (w, h), borderMode=cv2.BORDER_REPLICATE)
        predicted = self.points if identity else _apply(guess, self.points).astype(np.float32)
        inside = ((predicted[:, 0] > 4) & (predicted[:, 0] < w-5) &
                  (predicted[:, 1] > 4) & (predicted[:, 1] < h-5))
        if inside.sum() < MIN_TRACKED:
            return None
        start = np.ascontiguousarray(predicted[inside]).reshape(-1, 1, 2)
        source = self.points[inside]
        found, ok, _ = cv2.calcOpticalFlowPyrLK(warped, gray, start, None, **LK)
        if found is None:
            return None
        back, reverse, _ = cv2.calcOpticalFlowPyrLK(gray, warped, found, None, **LK)
        if back is None:
            return None
        good = (ok.ravel() > 0) & (reverse.ravel() > 0)
        good &= np.linalg.norm((back-start).reshape(-1, 2), axis=1) < 1.
        if good.sum() < MIN_TRACKED or good.mean() < .3:
            return None
        matrix, inliers = cv2.estimateAffinePartial2D(
            source[good], found.reshape(-1, 2)[good], method=cv2.RANSAC,
            ransacReprojThreshold=1.5, maxIters=200, confidence=.995, refineIters=10)
        if matrix is None or not np.isfinite(matrix).all():
            return None
        if inliers.sum() < MIN_TRACKED or inliers.mean() < .6:
            return None
        scale = float(np.hypot(matrix[0, 0], matrix[1, 0]))
        if not .4 <= scale <= 2.5:
            return None
        # The scanned scene must still be largely in view and look the same:
        # rejects unrelated scenes even when a few features happen to agree.
        aligned = cv2.warpAffine(self.reference, matrix, (w, h))
        mask = cv2.warpAffine(np.full((h, w), 255, np.uint8), matrix, (w, h),
                              flags=cv2.INTER_NEAREST) > 0
        if mask.mean() < .25:
            return None
        difference = aligned.astype(np.int16) - gray
        difference = difference[mask]
        # Remove a global exposure change before judging similarity.
        if np.abs(difference - np.median(difference)).mean() > 20:
            return None
        return matrix


def move_points(points, matrix):
    """Apply a 2x3 affine to an (N, 2) point list."""
    return (np.asarray(points, dtype=float) @ matrix[:, :2].T + matrix[:, 2]).tolist()
