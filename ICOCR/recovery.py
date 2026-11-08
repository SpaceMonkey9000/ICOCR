"""Bounded, appearance-based reacquisition. Never runs OCR or changes identity."""
import time
import cv2
import numpy as np


class Recovery:
    GRACE = .75

    @staticmethod
    def gray(frame):
        h,w = frame.shape[:2]
        ratio = min(1.,480/max(h,w))
        size = (max(1,round(w*ratio)),max(1,round(h*ratio)))
        return cv2.cvtColor(cv2.resize(frame,size,interpolation=cv2.INTER_AREA),cv2.COLOR_BGR2GRAY)

    def __init__(self, frame, row, roi, now=None):
        self.started = time.monotonic() if now is None else now
        self.shape = frame.shape[:2]
        self.row = dict(row)
        self.roi = tuple(roi)
        self.previous = None
        self.hits = 0
        self.attempts = 0
        gray = self.gray(frame)
        self.ratio = np.array(gray.shape[::-1])/np.array(self.shape[::-1])
        pts = np.asarray(row['box'])*self.ratio
        lo = np.floor(pts.min(axis=0)-8).astype(int)
        hi = np.ceil(pts.max(axis=0)+8).astype(int)
        lo = np.maximum(lo,0);hi=np.minimum(hi,gray.shape[::-1])
        self.origin = lo
        self.template = gray[lo[1]:hi[1],lo[0]:hi[0]].copy()
        self.valid = (self.template.size > 0 and min(self.template.shape)>=10 and
                      float(self.template.std())>=10)

    def expired(self, now=None):
        return (not self.valid or (time.monotonic() if now is None else now)-self.started > self.GRACE)

    def locate(self, frame, roi, now=None):
        if self.expired(now) or frame.shape[:2] != self.shape or tuple(roi) != self.roi:
            self.valid = False
            return None
        gray = self.gray(frame)
        h,w = gray.shape
        a,b,c,d = roi
        x,y = max(0,int(a*w)),max(0,int(b*h))
        search = gray[y:min(h,int(d*h)),x:min(w,int(c*w))]
        th,tw = self.template.shape
        if search.shape[0] < th or search.shape[1] < tw:
            return None
        self.attempts += 1
        scores = cv2.matchTemplate(search,self.template,cv2.TM_CCOEFF_NORMED)
        _,best,_,position = cv2.minMaxLoc(scores)
        # Reject a competing location, including an identical neighbouring IC.
        px,py = position
        suppressed = scores.copy()
        rx,ry = max(3,tw//3),max(3,th//3)
        suppressed[max(0,py-ry):py+ry+1,max(0,px-rx):px+rx+1] = -1
        second = float(suppressed.max())
        if not np.isfinite(best) or best < .90 or best-second < .08:
            self.hits = 0;self.previous = None
            return None
        offset = np.array([px+x,py+y])-self.origin
        centre = np.asarray(self.row['box']).mean(axis=0)*self.ratio+offset
        if self.previous is not None and np.linalg.norm(centre-self.previous) < max(tw,th):
            self.hits += 1
        else:
            self.hits = 1
        self.previous = centre
        if self.hits < 2:
            return None
        moved = dict(self.row,box=(np.asarray(self.row['box'])+offset/self.ratio).tolist())
        if self.row.get('body_box') is not None:
            moved['body_box']=(np.asarray(self.row['body_box'])+offset/self.ratio).tolist()
        return moved
