"""Cheap conservative checks for reusing geometry on a stationary view.

This is a motion gate, not optical-flow tracking. Changed views lose overlays
until a worker supplies fresh geometry. References stay anchored to inference.
"""
import cv2
import numpy as np


SIGNATURE_SIZE = (160, 96)
PRE_WIDTH = 640


def signature(frame):
    """160x96 grey thumbnail used to compare views.

    0.8.4.3: a single INTER_LINEAR step samples only a few source pixels per
    output pixel, so camera sensor noise alone could exceed the stationary
    thresholds and defeat detect_cached and overlay reuse. A cheap linear
    step to ~640 px wide followed by INTER_AREA averages the noise away.
    """
    h, w = frame.shape[:2]
    if w > PRE_WIDTH:
        frame = cv2.resize(frame, (PRE_WIDTH, max(SIGNATURE_SIZE[1], round(h*PRE_WIDTH/w))),
                           interpolation=cv2.INTER_LINEAR)
    small = cv2.resize(frame, SIGNATURE_SIZE, interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)


def stationary(before, after):
    if before is None or after is None or before.shape != after.shape:
        return False
    delta = np.abs(before - after)
    tiles = delta.reshape(6, 16, 10, 16).mean(axis=(1, 3))
    return (float(delta.mean()) <= 1.5 and float(tiles.max()) <= 6.0 and
            float((delta > 20).mean()) <= .005)


def matching_frames(source, current):
    return (source is current or (source is not None and current is not None and
            source.shape == current.shape and stationary(signature(source), signature(current))))
