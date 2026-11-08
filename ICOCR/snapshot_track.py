"""Carry an immutable OCR snapshot into current video coordinates."""
from config_loader import tuning
import cv2
import numpy as np
from ic_tracker import ICTracker
from scene_guard import scene_signature, scene_changed
from ocr_core import crop_roi


class SnapshotTrack:
    def __init__(self, frame, roi):
        self.source = frame.copy()
        self.roi = tuple(roi)
        h,w = frame.shape[:2]
        self.offset = np.array([int(roi[0]*w), int(roi[1]*h)])
        self.signature = scene_signature(crop_roi(frame,roi))
        self.tracker = ICTracker()
        margin = max(4., w/960*4)
        x1,y1 = np.maximum([roi[0]*w,roi[1]*h], margin)
        x2,y2 = np.minimum([roi[2]*w,roi[3]*h], [w-margin,h-margin])
        box = [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
        self.tracker.start(frame, dict(box=box))
        self.last_frame = frame
        self.lost = False

    def update(self, frame, gray=None):
        """gray: optional precomputed tracking grey of frame (shared per frame)."""
        if frame is self.last_frame:
            return
        self.last_frame = frame
        if self.tracker.active:
            if not self.tracker.update(frame, gray):
                self.lost = True
        elif frame.shape != self.source.shape or scene_changed(
                self.signature, scene_signature(crop_roi(frame,self.roi))):
            self.lost = True

    def resolve(self, row, frame):
        """Return a full-frame row only if its marking still matches visually."""
        self.update(frame)
        if self.lost or frame.shape != self.source.shape:
            return None
        box = np.asarray(row['box'],np.float32) + self.offset
        body = (np.asarray(row['body_box'],np.float32)+self.offset
                if row.get('body_box') is not None else None)
        tracker = self.tracker
        if not tracker.active:
            result = dict(row,box=box.tolist())
            if body is not None:
                result['body_box'] = body.tolist()
            return result  # Stationary, feature-poor snapshot.
        ratio = tracker.ratio
        small_box = box * ratio
        mapped = cv2.transform(small_box[None],tracker.matrix[:2])[0]
        gray = tracker.gray(frame)
        h,w = gray.shape
        if (mapped[:,0].min()<2 or mapped[:,1].min()<2 or
                mapped[:,0].max()>w-3 or mapped[:,1].max()>h-3):
            return None
        # Validate the marking itself, not just the surrounding PCB used by flow.
        source_gray = tracker.gray(self.source)
        lo = np.maximum(np.floor(small_box.min(axis=0)-3).astype(int),0)
        hi = np.minimum(np.ceil(small_box.max(axis=0)+3).astype(int),[w,h])
        x,y = lo; right,bottom = hi
        template = source_gray[y:bottom,x:right]
        if min(template.shape)<5 or template.std()<3:
            return None
        inverse = np.linalg.inv(tracker.matrix)
        inverse[:2,2] -= lo
        aligned = cv2.warpAffine(gray,inverse[:2],(right-x,bottom-y))
        score = float(cv2.matchTemplate(aligned,template,cv2.TM_CCOEFF_NORMED)[0,0])
        if not np.isfinite(score) or score<tuning('tracking.snapshot_correlation'):
            return None
        result = dict(row,box=(mapped/ratio).tolist())
        if body is not None:
            result['body_box'] = (cv2.transform((body*ratio)[None],tracker.matrix[:2])[0]/ratio).tolist()
        return result
