"""Single-owner tracking worker with ordered commands and a latest-frame mailbox.

Published boxes always accompany the exact frame they describe. UI invalidation
changes the generation immediately; old work can finish but cannot be published.
"""
from collections import deque
import logging
import threading
import time
import numpy as np
from ic_tracker import ICTracker, tracking_gray
from recovery import Recovery
from snapshot_track import SnapshotTrack
from scene_guard import scene_signature, scene_changed
from ocr_core import crop_roi


class TrackingWorker:
    def __init__(self):
        self.condition = threading.Condition()
        self.commands = deque()
        self.pending_frame = None
        self.desired_epoch = 0
        self.closed = False
        self.published = None
        self.version = 0
        self._reset(0)
        self.thread = threading.Thread(target=self._run, name='tracking', daemon=True)
        self.thread.start()

    def _reset(self, epoch):
        self.epoch = epoch
        self.tracker = ICTracker()
        self.acquisition = None
        self.acquisition_id = None
        self.resolved_request = None
        self.resolution = ''
        self.held = None
        self.hold_signature = None
        self.frame = None
        self.frame_id = -1
        self.roi = (0, 0, 1, 1)
        self.error = ''
        self.recovery = None
        self.recovery_count = 0
        self.recovery_ms = 0.
        self.recovery_search_ms = 0.

    def reset(self, epoch):
        with self.condition:
            self.desired_epoch = epoch
            self.commands.clear()
            self.pending_frame = None
            self.published = None
            self.commands.append(('reset', epoch))
            self.condition.notify()

    def begin(self, epoch, request_id, frame_id, frame, roi):
        self._command(('begin', epoch, request_id, frame_id, frame, tuple(roi)))

    def resolve(self, epoch, request_id, row):
        self._command(('resolve', epoch, request_id, row))

    def _command(self, command):
        with self.condition:
            if not self.closed and command[1] == self.desired_epoch:
                self.commands.append(command)
                self.condition.notify()

    def submit(self, epoch, frame_id, frame, roi):
        with self.condition:
            if not self.closed and epoch == self.desired_epoch:
                self.pending_frame = (epoch, frame_id, frame, tuple(roi))
                self.condition.notify()

    def snapshot(self):
        with self.condition:
            return self.published

    def close(self, timeout=5.):
        """Stop the worker; False if it is still running after ``timeout`` s."""
        with self.condition:
            self.closed = True
            self.commands.clear()
            self.pending_frame = None
            self.condition.notify()
        self.thread.join(timeout)
        return not self.thread.is_alive()

    def _advance(self, frame_id, frame, roi):
        if frame_id <= self.frame_id:
            return
        self.roi = roi
        self.recovery_search_ms = 0.
        previous_row = self.tracker.row if self.tracker.active else self.held
        previous_frame = self.frame
        # 0.8.4.3: one tracking grey per frame, shared by the tracker, the
        # snapshot tracker and a recovered tracker's start (computed lazily).
        shared = []
        def gray():
            if not shared:
                shared.append(tracking_gray(frame))
            return shared[0]
        if self.tracker.active:
            self.tracker.update(frame, gray())
        if self.acquisition is not None and self.acquisition.tracker.active and frame is not self.acquisition.last_frame:
            self.acquisition.update(frame, gray())
        elif self.acquisition is not None:
            self.acquisition.update(frame)
        if self.held is not None:
            if (frame.shape != self.frame.shape or scene_changed(self.hold_signature,
                    scene_signature(crop_roi(frame, self.roi)))):
                self.held = None
                self.hold_signature = None
        if (previous_row is not None and not self.tracker.active and self.held is None
                and previous_frame is not None and self.recovery is None):
            h,w = previous_frame.shape[:2]
            centre = np.asarray(previous_row['box']).mean(axis=0)/[w,h]
            if roi[0] <= centre[0] <= roi[2] and roi[1] <= centre[1] <= roi[3]:
                self.recovery = Recovery(previous_frame, previous_row, roi)
        if self.recovery is not None:
            started = time.perf_counter()
            row = self.recovery.locate(frame, roi)
            if row is not None:
                replacement = ICTracker()
                if replacement.start(frame, row, gray()):
                    self.tracker = replacement
                    self.recovery_count += 1
                    self.recovery_ms = (time.monotonic()-self.recovery.started)*1000
                    self.recovery = None
                    self.resolution = 'recovered'
            if self.recovery is not None and self.recovery.expired():
                self.recovery = None
                self.resolution = 'lost'
            self.recovery_search_ms = (time.perf_counter()-started)*1000
        self.frame, self.frame_id = frame, frame_id

    def _handle(self, command):
        kind, epoch, *args = command
        if kind == 'reset':
            self._reset(epoch)
            return
        if epoch != self.epoch:
            return
        if kind == 'begin':
            self.recovery = None
            request_id, frame_id, frame, roi = args
            self.error = ''
            self.acquisition_id = request_id
            self.acquisition = SnapshotTrack(frame, roi)
            self.resolution = ''
            # The UI may have requested a snapshot older than our latest frame.
            if self.frame is not None and self.frame_id > frame_id:
                self.acquisition.update(self.frame)
            else:
                self._advance(frame_id, frame, roi)
        elif kind == 'resolve':
            request_id, candidate = args
            if request_id != self.acquisition_id:
                return
            row = (self.acquisition.resolve(candidate, self.frame)
                   if candidate is not None and self.acquisition is not None
                   and self.frame is not None else None)
            self.resolved_request = request_id
            self.resolution = 'lost' if candidate is not None else 'empty'
            if row is not None:
                replacement = ICTracker()
                if replacement.start(self.frame, row):
                    self.tracker = replacement
                    self.held = None
                    self.resolution = 'tracking'
                elif not self.tracker.active:
                    self.held = row
                    self.hold_signature = scene_signature(crop_roi(self.frame, self.roi))
                    self.resolution = 'held'
            self.acquisition = None
            self.acquisition_id = None

    def _publish(self, elapsed):
        row = self.tracker.row if self.tracker.active else self.held
        inside = False
        if row is not None and self.frame is not None:
            h, w = self.frame.shape[:2]
            centre = np.asarray(row['box']).mean(axis=0) / [w, h]
            inside = self.roi[0] <= centre[0] <= self.roi[2] and self.roi[1] <= centre[1] <= self.roi[3]
        with self.condition:
            if self.closed or self.epoch != self.desired_epoch:
                return
            self.version += 1
            self.published = dict(epoch=self.epoch, version=self.version,
                frame_id=self.frame_id, frame=self.frame, row=row, inside=inside,
                tracked=self.tracker.active, acquiring=self.acquisition_id,
                acquisition_lost=bool(self.acquisition is not None and self.acquisition.lost),
                recovering=self.recovery is not None, recovery_count=self.recovery_count,
                recovery_ms=self.recovery_ms, recovery_search_ms=self.recovery_search_ms,
                resolved_request=self.resolved_request, resolution=self.resolution,
                milliseconds=elapsed*1000, completed=time.monotonic(), error=self.error)

    def _run(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.closed or self.commands or self.pending_frame is not None)
                if self.closed:
                    return
                command = self.commands.popleft() if self.commands else None
                frame = None
                if command is None:
                    frame, self.pending_frame = self.pending_frame, None
                desired = self.desired_epoch
            started = time.perf_counter()
            try:
                if command is not None and command[1] == desired:
                    self._handle(command)
                elif frame is not None and frame[0] == self.epoch == desired:
                    self._advance(*frame[1:])
            except Exception as exc:
                logging.exception('Tracking worker failed')
                self.tracker.reset()
                self.recovery = None
                self.held = None
                self.resolved_request = self.acquisition_id
                self.acquisition = None
                self.acquisition_id = None
                self.resolution = 'lost'
                self.error = str(exc)
            self._publish(time.perf_counter()-started)
