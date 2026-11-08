"""Latest-frame overlay mailbox. All image processing stays off the Tk thread."""
import logging
import threading
import time
import weakref
import numpy as np
from overlay_motion import transform, FrameCache


def compose(after, before):
    return (np.vstack([after, [0.,0.,1.]]) @ np.vstack([before, [0.,0.,1.]]))[:2]


class OverlayWorker:
    def __init__(self):
        self.condition = threading.Condition()
        self.closed = False
        self.epoch = 0
        self.pending = None
        self.result = None
        self.last_submission = None
        self.thread = threading.Thread(target=self._run, name='overlay-motion', daemon=True)
        self.thread.start()

    def reset(self, epoch):
        with self.condition:
            self.epoch = epoch
            self.pending = self.result = self.last_submission = None
            self.condition.notify_all()

    def submit(self, epoch, frame, sources, payload=None):
        sources = tuple(s for i,s in enumerate(sources) if s is not None and
                        not any(s is old for old in sources[:i]))
        key = (epoch, id(frame), tuple(id(s) for s in sources))
        with self.condition:
            if not self.closed and epoch == self.epoch and key != self.last_submission:
                self.pending = (epoch, frame, sources, time.monotonic(), payload)
                self.last_submission = key
                self.condition.notify()

    def snapshot(self):
        with self.condition:
            return self.result

    def matrix(self, epoch, source, current):
        if source is current:
            return np.eye(2, 3)
        state = self.snapshot()
        if (not state or state['epoch'] != epoch or current is None or
                state['frame'].shape != current.shape or
                time.monotonic()-state['submitted'] > .18):
            return None
        # Published coordinates can lag the camera by a few frames; never
        # replace the current video with the worker's older image.
        for old, matrix in state['anchors']:
            if old is source:
                return matrix
        return None

    def close(self, timeout=5.):
        """Stop the worker; False if it is still running after ``timeout`` s."""
        with self.condition:
            self.closed = True
            self.pending = None
            self.condition.notify_all()
        self.thread.join(timeout)
        return not self.thread.is_alive()

    def _run(self):
        previous = None
        anchors = []
        history = []
        epoch = None
        steps = 0
        # 0.8.4.3: thumbnails/features of recent frames are reused (the current
        # frame is the next step's previous frame; anchors reuse sources).
        cache = FrameCache()
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.closed or self.pending is not None)
                if self.closed:
                    return
                generation, frame, sources, submitted, payload = self.pending
                self.pending = None
            started = time.perf_counter()
            if generation != epoch:
                previous, anchors, history, steps = None, [], [], 0
                epoch = generation
            try:
                # One consecutive-frame transform advances both text and body.
                # Reanchor every eight processed frames to bound accumulated drift.
                step = (transform(previous, frame, cache) if previous is not None and
                        sources and steps % 8 else None)
                # 0.8.3.2: weak references. A frame that nothing else holds can
                # never be submitted as a source again, so its entry is dropped
                # instead of keeping up to eight full frames (~200 MB at 4K) alive.
                history = ([(s, compose(step, m)) for s,m in history if s() is not None][-7:]
                           if step is not None else [])
                history.append((weakref.ref(frame), np.eye(2,3)))
                updated = []
                for source in sources:
                    prior = next((m for s,m in anchors if s is source), None)
                    matrix = next((m for s,m in history if s() is source), None)
                    if matrix is None:
                        matrix = (compose(step, prior) if step is not None and prior is not None
                                  else transform(source, frame, cache))
                    updated.append((source, matrix))
                anchors, previous = updated, frame
                steps += 1
                result = dict(epoch=epoch, frame=frame, anchors=anchors,
                              submitted=submitted, payload=payload, milliseconds=(time.perf_counter()-started)*1000)
            except Exception:
                logging.exception('Overlay motion failed')
                anchors, history, previous = [], [], None
                result = dict(epoch=epoch, frame=frame, anchors=[], submitted=submitted, payload=None,
                              milliseconds=(time.perf_counter()-started)*1000)
            with self.condition:
                if self.epoch == epoch:
                    self.result = result
