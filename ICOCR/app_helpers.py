"""Tk-independent helpers used by the ICOCR controller (split from app.py in 0.8.4.8)."""
import logging
import time

import cv2
import numpy as np

from ic_preprocessing import preprocess


class Value:
    """Plain stand-in for a Tk variable (get/set) used before the window is built.

    App._init_state gives every setting and status field one of these, so all
    defaults live in one place and controller code never needs hasattr/getattr
    guards. LayoutMixin.build replaces them with real Tk variables that start
    from the same values.
    """
    __slots__ = ('value',)

    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def preview_resize(frame, size):
    """Display-only downscale (0.8.3.2; 0.8.8 halving).

    Repeated exact 2x INTER_AREA halving while the image is at least twice the
    target, then one INTER_LINEAR step for the remaining <2x. OpenCV's 2x
    INTER_AREA path is much faster than its general integer-factor path:
    measured with OpenCV 4.11 on 2 threads, 4K -> 1036x583 took 8-12 ms per
    frame on the Tk thread with the former integer-factor INTER_AREA +
    INTER_LINEAR (its note claimed ~2 ms) and takes 2.5-3.5 ms now; 4K -> 960x540
    5-9 -> 2-2.5 ms. The result is closer to a single (slow, 17-26 ms) INTER_AREA
    resize than before (4K board photo: 42.5 -> 45.6 dB PSNR). An odd edge
    row/column is dropped before each halving (exact 2x keeps the fast path;
    invisible on screen). OCR, captures and logs never use this image.
    """
    h, w = frame.shape[:2]
    dw, dh = size
    while w >= 2 * dw and h >= 2 * dh:
        frame = cv2.resize(frame[:h - h % 2, :w - w % 2], (w // 2, h // 2), interpolation=cv2.INTER_AREA)
        h, w = frame.shape[:2]
    if w == dw and h == dh:
        return frame
    return cv2.resize(frame, (dw, dh), interpolation=cv2.INTER_LINEAR)


def roi_view(frame, roi):
    """Selection as a view into the frame (no copy) for read-only checks such as
    the scene guard; OCR requests still use crop_roi, which copies."""
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = roi
    return frame[max(0, int(y1*h)):min(h, int(y2*h)), max(0, int(x1*w)):min(w, int(x2*w))]


SNAPSHOT_PREVIEW = (290, 150)
_UNSET = object()


def snapshot_preview_size(w, h, box=SNAPSHOT_PREVIEW):
    """Final size of the sidebar snapshot preview.

    Until 0.8.4.2 the preview was resized to fit 580x300 and then reduced again
    with PIL's Image.thumbnail to fit 290x150. This returns the size that two-step
    process produced, so the single resize gives the same layout.
    """
    scale = min(1., 580/w, 300/h)
    w, h = max(1, int(w*scale)), max(1, int(h*scale))
    x, y = box
    if x >= w and y >= h:
        return w, h
    aspect = w / h
    def round_aspect(number, key):   # as in PIL.Image.thumbnail
        return max(min(int(np.floor(number)), int(np.ceil(number)), key=key), 1)
    if x / y >= aspect:
        x = round_aspect(y * aspect, key=lambda n: abs(aspect - n / y))
    else:
        y = round_aspect(x / aspect, key=lambda n: 0 if n == 0 else abs(aspect - x / n))
    return x, y


def preview_preprocessed(snapshot, preset, values=None, box=SNAPSHOT_PREVIEW):
    """Preview image: downscale once (INTER_AREA), then preprocess the small image.

    Preprocessing the full snapshot first and resizing twice cost tens of
    milliseconds per scan on 4K selections. The Illumination background blur is
    in pixels, so its sigma is scaled with the image to keep the same look.
    """
    h, w = snapshot.shape[:2]
    size = snapshot_preview_size(w, h, box)
    factor = min(size[0]/w, size[1]/h)
    small = snapshot
    if size != (w, h):
        step = int(min(w / size[0], h / size[1]))
        if step >= 2:
            # Integer-factor INTER_AREA is OpenCV's fast path (block average);
            # the at most step-1 trimmed edge pixels are invisible in a preview.
            small = cv2.resize(small[:h - h % step, :w - w % step], (w // step, h // step),
                               interpolation=cv2.INTER_AREA)
        small = cv2.resize(small, size, interpolation=cv2.INTER_AREA)
    if values is not None and preset in ('Illumination', 'Lighting correction') and factor < 1:
        values = dict(values, background_sigma=max(1., float(values.get('background_sigma', 21.)) * factor))
    return preprocess(small, preset, values)


def display_text(row):
    """Text placed in the marking field (and searched) for a list row."""
    if row.get('ocr_correction') and row.get('resolved_partnumber'):
        return row['resolved_partnumber']
    return row.get('text') if row.get('raw_line') else row['key']


def set_if_changed(variable, value):
    """Set a Tk variable only when its value changes; an unchanged write still
    runs traces and label relayout on every tick."""
    try:
        if variable.get() == value:
            return False
    except Exception:
        pass
    variable.set(value)
    return True


class ItemPool:
    """Pooled canvas items by kind (polygon, rectangle, text): reused each frame,
    surplus items hidden (0.8.3.2 behaviour of the detector and chip overlays)."""
    def __init__(self, canvas, tag, raise_items=False):
        self.canvas, self.tag, self.raise_items = canvas, tag, raise_items
        self.pools = {}
        self.used = {}

    def begin(self):
        self.used = {}

    def item(self, kind, coords, **options):
        pool = self.pools.setdefault(kind, [])
        index = self.used.get(kind, 0)
        self.used[kind] = index + 1
        if index < len(pool):
            self.canvas.coords(pool[index], *coords)
            self.canvas.itemconfigure(pool[index], state='normal', **options)
            if self.raise_items:
                self.canvas.tag_raise(pool[index])
            return pool[index]
        created = getattr(self.canvas, 'create_'+kind)(*coords, tags=self.tag, **options)
        pool.append(created)
        return created

    def finish(self):
        for kind, pool in self.pools.items():
            for unused in pool[self.used.get(kind, 0):]:
                self.canvas.itemconfigure(unused, state='hidden')


class ErrorLimiter:
    """Log the first occurrence of an error with its traceback, then only a
    count while the same error repeats (a broken tick runs ~30 times a second)."""
    def __init__(self, interval=30.):
        self.interval = interval
        self.key = None
        self.repeats = 0
        self.logged_at = 0.

    def report(self, exc, now=None, context='UI tick failed'):
        """Log exc; returns True when this is a new (not repeated) error."""
        now = time.monotonic() if now is None else now
        key = (type(exc).__name__, str(exc))
        if key == self.key and now - self.logged_at < self.interval:
            self.repeats += 1
            return False
        if key == self.key and self.repeats:
            logging.error('%s: previous error repeated %d more time(s)', context, self.repeats)
        new = key != self.key
        self.key, self.repeats, self.logged_at = key, 0, now
        logging.error(context, exc_info=(type(exc), exc, exc.__traceback__))
        return new

