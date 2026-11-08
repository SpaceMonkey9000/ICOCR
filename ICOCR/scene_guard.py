"""Scene stability guard for acquisition; ReadingVote owns text confirmation."""
from config_loader import tuning
import cv2
import numpy as np


def scene_signature(crop):
    small = cv2.resize(crop, (160, 96), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)


def scene_changed(before, after):
    delta = np.abs(before - after)
    # Local tiles also catch a small moving chip in a mostly unchanged region.
    tiles = delta.reshape(6, 16, 10, 16).mean(axis=(1, 3))
    return float(delta.mean()) > tuning('tracking.scene_mean_change') or float(tiles.max()) > tuning('tracking.scene_tile_change')


class SceneGuard:
    def __init__(self):
        self.reset()

    def reset(self):
        self.anchor = None
        self.stable_since = None

    def observe(self, crop, now):
        sig = scene_signature(crop)
        moved = self.anchor is not None and scene_changed(self.anchor, sig)
        if self.anchor is None or moved:
            self.anchor = sig
            self.stable_since = now
        return moved

    def ready(self, now):
        return self.stable_since is not None and now - self.stable_since >= tuning('timing.scene_settle_seconds')

