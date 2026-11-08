"""Low-cost scene inactivity monitor; no Tk or worker ownership."""
import cv2
import numpy as np


def thumbnail(frame, size=(160, 90), oversample=4):
    """INTER_AREA thumbnail of a strided view (0.8.8).

    Resizing 4K straight to 160x90 cost 6-8 ms every 0.2 s on the Tk thread.
    Taking every n-th pixel first, so ``oversample`` x ``oversample`` samples
    still average into each thumbnail pixel, costs ~1.3 ms. On 4K sample frames
    noise, exposure and JPEG re-encoding still give 0 changed pixels, a 2 px
    shift stays below the threshold and larger shifts change by at most ~0.01
    (e.g. 24 px: 0.249 -> 0.249); a plain stride (no averaging) made 2 px
    shifts look like motion.
    """
    h, w = frame.shape[:2]
    step = max(1, min(h // (size[1]*oversample), w // (size[0]*oversample)))
    return cv2.resize(frame[::step, ::step], size, interpolation=cv2.INTER_AREA)


class IdleSleep:
    INTERVAL = .2
    PIXEL_DELTA = 12
    CHANGED_FRACTION = .006

    def __init__(self):
        self.reset()

    def reset(self, now=None):
        self.sleeping = False
        self.anchor = None
        self.last_activity = now
        self.last_check = None
        self.last_frame = None

    def touch(self, now):
        was_sleeping = self.sleeping
        self.reset(now)
        return was_sleeping

    def observe(self, frame, frame_id, now, timeout=120., enabled=True, can_sleep=True):
        if not enabled or frame is None:
            return 'wake' if self.touch(now) else None
        if self.last_activity is None:
            self.last_activity = now
        if frame_id == self.last_frame or (self.last_check is not None and now-self.last_check < self.INTERVAL):
            return None
        self.last_check, self.last_frame = now, frame_id
        small = thumbnail(frame)
        if small.ndim == 3:
            small = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        small = cv2.GaussianBlur(small, (5, 5), 0).astype(np.float32)
        if self.anchor is None:
            self.anchor = small
            return None
        delta = small-self.anchor
        # Remove uniform exposure offsets; compare to a fixed anchor so slow
        # board motion accumulates instead of disappearing between samples.
        delta -= np.median(delta)
        moved = float(np.mean(np.abs(delta) > self.PIXEL_DELTA)) >= self.CHANGED_FRACTION
        if moved:
            self.anchor = small
            self.last_activity = now
            if self.sleeping:
                self.sleeping = False
                return 'wake'
        elif can_sleep and not self.sleeping and now-self.last_activity >= timeout:
            self.sleeping = True
            return 'sleep'
        return None
