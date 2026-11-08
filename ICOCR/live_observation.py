"""Opt-in live observation scheduler. No OCR or database work on the UI thread.

Quality thresholds are prototype heuristics, not calibrated probabilities.
One best recent frame is retained; no unbounded frame or inference queue.
"""
from config_loader import tuning
from dataclasses import dataclass
import cv2
import numpy as np
from reading_vote import ReadingVote


@dataclass
class Sample:
    frame: object
    frame_id: int
    at: float
    box: object
    quality: float
    signature: object
    usable: bool


def measure(frame, box=None, roi=None):
    if box is not None:
        points = np.asarray(box, np.float32)
        if points.shape != (4, 2) or not np.isfinite(points).all():
            return 0., None, False
        if abs(cv2.contourArea(points)) < 24:
            return 0., None, False
        target = np.float32([[0,0],[159,0],[159,47],[0,47]])
        crop = cv2.warpPerspective(frame, cv2.getPerspectiveTransform(points, target), (160,48))
    else:
        h,w = frame.shape[:2]
        a,b,c,d = roi or (0,0,1,1)
        crop = frame[max(0,int(b*h)):min(h,int(d*h)),max(0,int(a*w)):min(w,int(c*w))]
        if crop.size == 0:
            return 0., None, False
        crop = cv2.resize(crop, (256,144), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    low,high = np.percentile(gray, (1,99))
    contrast = float(high-low)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_32F).var())
    glare = float(np.mean(gray >= 250))
    quality = sharpness * min(1.,contrast/50.) * (1.-.8*glare)
    signature = cv2.resize(gray, (64,24), interpolation=cv2.INTER_AREA).astype(np.float32)
    # Normalize global lighting, but preserve local changes in the marking.
    signature = (signature-float(signature.mean())) / max(12.,float(signature.std())) * 32.
    return quality, signature, contrast >= 8. and sharpness >= 6. and glare < .65


def changed(before, after):
    if before is None or after is None:
        return False
    delta = np.abs(before-after)
    tiles = delta.reshape(3,8,8,8).mean(axis=(1,3))
    return float(delta.mean()) > 15. or float(tiles.max()) > 32.


class ObservationPolicy:
    SAMPLE_INTERVAL = tuning('timing.sample_interval')
    SETTLE = tuning('timing.settle')
    MAX_AGE = tuning('timing.max_age')
    LINE_INTERVAL = tuning('timing.line_interval')
    MAX_FULL_SCANS = tuning('timing.max_full_scans')
    MAX_LINE_READS = tuning('timing.max_line_reads')
    INITIAL_LINE_READS = tuning('timing.initial_line_reads')
    IMPROVEMENT = tuning('timing.improvement')

    def __init__(self):
        self.reset()

    def reset(self):
        self.full_scans = 0
        self.full_quality = 0.
        self.full_signature = None
        self.line_reads = 0
        self.line_quality = 0.
        self.next_line = 0.
        self.best = None
        self.last_sample = None
        self.sampled_id = None
        self.last_sample_at = -float('inf')
        self.started = None
        self.used_frames = set()
        self.stable = False
        self.anchor = None
        self.change_since = None
        self.reason = 'Waiting for a clear, stable view'

    def start_track(self):
        self.line_reads = 0
        self.line_quality = 0.
        self.next_line = 0.
        self.best = None
        self.last_sample = None
        self.sampled_id = None
        self.last_sample_at = -float('inf')
        self.used_frames.clear()
        self.stable = False
        self.anchor = None
        self.change_since = None
        self.reason = 'Checking tracked marking'

    def observe(self, frame, frame_id, now, *, box=None, roi=None):
        if frame_id == self.sampled_id or now-self.last_sample_at < self.SAMPLE_INTERVAL:
            return False
        self.sampled_id = frame_id
        self.last_sample_at = now
        if self.started is None:
            self.started = now
        quality, signature, usable = measure(frame, box, roi)
        sample = Sample(frame, frame_id, now, box, quality, signature, usable)
        self.last_sample = sample
        if self.best is not None and now-self.best.at > self.MAX_AGE:
            self.best = None
        if usable and frame_id not in self.used_frames and (
                self.best is None or self.best.frame_id in self.used_frames or quality > self.best.quality):
            self.best = sample
        if box is not None and usable:
            if self.anchor is None:
                self.anchor = signature
            if changed(self.anchor, signature):
                if self.change_since is None:
                    self.change_since = now
                elif now-self.change_since >= .1:
                    self.reason = 'Tracked marking changed'
                    return True
            else:
                self.change_since = None
        return False

    def acquisition(self, now):
        sample = self.best
        if sample is None or now-sample.at > self.MAX_AGE or self.started is None or now-self.started < self.SETTLE:
            self.reason = 'Waiting for a clear, stable view'
            return None
        if self.full_scans >= self.MAX_FULL_SCANS:
            self.reason = 'Unresolved; full-scan limit reached'
            return None
        if self.full_scans and (sample.quality < self.full_quality*self.IMPROVEMENT or
                               not changed(self.full_signature, sample.signature)):
            self.reason = 'Unresolved; waiting for a better view'
            return None
        return sample

    def record_acquisition(self, sample):
        self.full_scans += 1
        self.full_quality = sample.quality
        self.full_signature = sample.signature
        self.reason = 'Acquiring marking'

    def refinement(self, now):
        if self.stable:
            self.reason = 'Stable marking; tracking only'
            return None
        if self.line_reads >= self.MAX_LINE_READS:
            self.reason = 'Unresolved; line-read limit reached'
            return None
        sample = self.best
        if now < self.next_line or sample is None or now-sample.at > self.MAX_AGE or sample.frame_id in self.used_frames:
            return None
        if self.line_reads >= self.INITIAL_LINE_READS and sample.quality < self.line_quality*self.IMPROVEMENT:
            self.reason = 'Uncertain marking; waiting for a sharper view'
            return None
        return sample

    def record_refinement(self, sample, now):
        self.line_reads += 1
        self.line_quality = max(self.line_quality, sample.quality)
        self.next_line = now+self.LINE_INTERVAL
        self.used_frames.add(sample.frame_id)
        self.reason = 'Checking tracked marking'

    def snapshot(self):
        return dict(prototype=True, full_scans=self.full_scans, line_reads=self.line_reads,
                    stable=self.stable, state=self.reason,
                    quality=self.last_sample.quality if self.last_sample else None)


class ObservedVote(ReadingVote):
    """Only exact observed strings; one vote per captured frame, no seed vote."""
    MIN_SCORE = .85
    MIN_SHARE = .75
    MAX_READS = ObservationPolicy.MAX_LINE_READS

    def __init__(self, row):
        super().__init__(row, seed=False)
        self.frames = set()

    def add(self, reading, frame_id=None):
        if frame_id is None or frame_id in self.frames:
            return None
        self.frames.add(frame_id)
        return super().add(reading, frame_id)

    def character_consensus(self):
        return None
