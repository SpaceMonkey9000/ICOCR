"""Camera preview pipeline, entirely off the GUI thread.

For every camera frame one worker thread: reduces it to preview size, applies
focus peaking if enabled, registers each active recognition overlay against
that same frame (``overlay_tracker``) and converts the preview to a QImage.
The GUI thread only swaps a pixmap and sets one transform, so the video stays
smooth while OCR runs and the overlay is always in step with the picture.

Only the newest result is kept: if the GUI is busy, frames are dropped rather
than queued, so the preview can never fall behind the camera.
"""
import logging
import threading
import time

import cv2
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from focus_peaking import overlay as focus_overlay
from overlay_tracker import OverlayTracker, tracking_gray

PREVIEW_LIMIT = (1280, 900)   # live preview size cap (width, height)
HOLD_SECONDS = .35            # keep the last overlay position this long after tracking is lost


def make_preview(frame, limit=PREVIEW_LIMIT):
    """Preview-size view of ``frame`` (the frame itself when already small)."""
    h, w = frame.shape[:2]
    scale = min(1., limit[0]/max(w, 1), limit[1]/max(h, 1))
    if scale >= 1.:
        return frame
    return cv2.resize(frame, (max(1, round(w*scale)), max(1, round(h*scale))),
                      interpolation=cv2.INTER_LINEAR)


def to_qimage(bgr):
    """Deep-copied QImage in the native 32-bit format (no conversion when it
    becomes a pixmap on the GUI thread)."""
    bgra = cv2.cvtColor(bgr, cv2.COLOR_BGR2BGRA)
    h, w = bgra.shape[:2]
    return QImage(bgra.data, w, h, int(bgra.strides[0]), QImage.Format.Format_RGB32).copy()


def render_image(frame, peaking=None, limit=PREVIEW_LIMIT):
    """QImage for ``frame``. ``peaking`` is None or the focus_peaking keyword
    arguments; ``limit=None`` keeps full resolution (still images)."""
    preview = frame if limit is None else make_preview(frame, limit)
    if peaking:
        preview = focus_overlay(preview, **peaking)
    return to_qimage(preview)


class PreviewWorker(QThread):
    """Consumes one ``Capture``; emits ``ready`` when a new result can be taken."""
    ready = Signal()

    def __init__(self, capture, parent=None):
        super().__init__(parent)
        self.capture = capture
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._peaking = None
        self._paused = False
        self._requests = []        # (epoch, frame) trackers to create
        self._wanted = set()       # epochs that should stay tracked
        self._result = None
        self._notified = False

    # -- GUI-thread API --------------------------------------------------------
    def set_peaking(self, options):
        with self._lock:
            self._peaking = dict(options) if options else None

    def set_paused(self, paused):
        with self._lock:
            self._paused = bool(paused)

    def track(self, epoch, frame):
        """Start following the scene of ``frame`` (the frame handed to a scan)."""
        with self._lock:
            self._wanted.add(epoch)
            self._requests.append((epoch, frame))

    def keep(self, epochs):
        """Stop tracking every epoch not listed."""
        with self._lock:
            self._wanted = set(epochs)
            self._requests = [r for r in self._requests if r[0] in self._wanted]

    def take(self):
        """Newest result dict (or None): frame, seq, image, matrices, status, fps, track_ms."""
        with self._lock:
            result, self._result = self._result, None
            self._notified = False
            return result

    def stop(self, timeout_ms=1500):
        self._stop.set()
        return self.wait(timeout_ms)

    # -- worker thread ---------------------------------------------------------
    def _publish(self, result):
        with self._lock:
            self._result = result
            notify = not self._notified
            self._notified = True
        if notify:
            self.ready.emit()

    def run(self):
        trackers = {}      # epoch -> [tracker, last matrix, time of last success]
        seq = -1
        last_status = None
        stamps = []
        while not self._stop.is_set():
            frame, new_seq, _, status = self.capture.wait(seq, .1)
            if self._stop.is_set():
                break
            with self._lock:
                paused, peaking = self._paused, self._peaking
                requests, self._requests = self._requests, []
                wanted = set(self._wanted)
            for epoch in [e for e in trackers if e not in wanted]:
                del trackers[epoch]
            if frame is None:
                if status != last_status:
                    last_status = status
                    self._publish(dict(frame=None, seq=new_seq, image=None, matrices={},
                                       status=status, fps=0., track_ms=0.))
                if self.capture.finished:
                    return
                continue
            try:
                for epoch, reference in requests:
                    if epoch in wanted:
                        trackers[epoch] = [OverlayTracker(make_preview(reference), reference.shape),
                                           None, 0.]
                if new_seq == seq:
                    continue          # timeout without a new frame
                if paused:
                    seq = new_seq     # frozen view: frames are skipped, trackers kept
                    continue
                seq = new_seq
                preview = make_preview(frame)
                started = time.perf_counter()
                now = time.monotonic()
                matrices, grays = {}, {}
                for epoch, entry in trackers.items():
                    tracker = entry[0]
                    if tracker.shape != frame.shape[:2]:
                        continue
                    if tracker.size not in grays:
                        grays[tracker.size] = tracking_gray(preview, tracker.size)
                    matrix = tracker.update(grays[tracker.size])
                    if matrix is not None:
                        entry[1], entry[2] = matrix, now
                    elif now - entry[2] > HOLD_SECONDS:
                        entry[1] = None
                    if entry[1] is not None:
                        matrices[epoch] = entry[1]
                track_ms = (time.perf_counter()-started)*1000 if trackers else 0.
                image = render_image(preview, peaking, limit=None)
                stamps = [t for t in stamps if now - t < 1.] + [now]
                last_status = status
                self._publish(dict(frame=frame, seq=seq, image=image, matrices=matrices,
                                   status=status, fps=float(len(stamps)), track_ms=track_ms))
            except Exception:
                # A preview failure must never take the camera down; drop the frame.
                logging.exception('Preview frame failed')
                seq = new_seq
                time.sleep(.05)
