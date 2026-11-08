"""Trained IC-body detector (YOLOv8 ONNX export described by its adjacent JSON specification).

The adapter returns the same dict as body_locator.locate_body so the OCR crop,
text-inside-body filter, outline and tracking use it unchanged. Upright (detect)
rotated-box (obb), and segmentation (segment) exports are supported; the JSON beside the model, or the
model's own metadata, says which. Scores are model confidences.
"""
import json
import logging
import time
import threading
from pathlib import Path
import cv2
import numpy as np

DETECTOR_ADAPTER_VERSION = 'segment-1'

from project_paths import DATA
MODEL_DIR = DATA/'models'


MODEL_NAMES = ('ic_body_obb.onnx', 'ic_body.onnx', 'ic_body_segment.onnx')


def default_model():
    """Prefer the rotated-box export when both are installed. The release
    uses DATA/models/ic_body_segment.onnx (0.8.4.3: found when it is the only one)."""
    for name in MODEL_NAMES:
        if (MODEL_DIR/name).exists():
            return MODEL_DIR/name
    return MODEL_DIR/'ic_body.onnx'


def _polygon(points):
    return cv2.convexHull(np.asarray(points, np.float32).reshape(-1, 2))


def body_for_selection(detections, roi, shape, started=None):
    """Body outline for the user's selection from whole-frame detections.

    roi is fractional (x1, y1, x2, y2). The detection covering most of the
    selection is used; it must lie fully inside the selection (and not be cut
    by the frame edge), otherwise the full selection is scanned. The returned
    box is in selection-crop pixels, like body_locator.locate_body.
    """
    h, w = shape[:2]
    x1, y1 = int(roi[0]*w), int(roi[1]*h)
    x2, y2 = min(w, int(roi[2]*w)), min(h, int(roi[3]*h))
    selection = _polygon([[x1, y1], [x2, y1], [x2, y2], [x1, y2]])
    result = dict(status='fallback', reason='Detector found no IC body in the selection', box=None,
                  score=0., source='model', candidate_count=len(detections))
    best, best_overlap, best_rank = None, 0., None
    selection_area = max(1., abs(cv2.contourArea(selection)))
    centre = np.array([(x1+x2)/2, (y1+y2)/2])
    for found in detections:
        body = _polygon(found.get('mask_polygon') or found.get('polygon') or
                        [[found['box'][0], found['box'][1]], [found['box'][2], found['box'][1]],
                         [found['box'][2], found['box'][3]], [found['box'][0], found['box'][3]]])
        area = abs(cv2.contourArea(body))
        if area <= 0:
            continue
        inter, _ = cv2.intersectConvexConvex(body, selection)
        fraction = inter / area
        distance = float(np.linalg.norm((body.reshape(-1, 2).mean(axis=0)-centre) /
                                       [max(1, x2-x1), max(1, y2-y1)]))
        eligible = fraction >= .98 and not found.get('truncated')
        rank = (eligible, inter / selection_area - .25*distance, found['score'])
        if fraction > .2 and (best_rank is None or rank > best_rank):
            best, best_overlap, best_rank = found, fraction, rank
    if best is not None and best_overlap > .2:
        result['score'] = best['score']
        corners = np.asarray(best.get('polygon') or
                             [[best['box'][0], best['box'][1]], [best['box'][2], best['box'][1]],
                              [best['box'][2], best['box'][3]], [best['box'][0], best['box'][3]]], float)
        if best.get('truncated'):
            result['reason'] = 'Detected IC body is cut off by the frame edge'
        elif best_overlap < .98:
            result['reason'] = 'Detected IC body extends beyond the selection — enlarge it or click the box'
        else:
            result.update(status='detected', reason='Detector IC body',
                          box=(corners-[x1, y1]).tolist(), angle=best.get('angle', 0.))
            if best.get('mask_polygon'):
                result.update(mask_polygon=(np.asarray(best['mask_polygon'])-[x1,y1]).tolist(),
                              task='segment',geometry=best.get('geometry'))
    result['milliseconds'] = (time.perf_counter()-started)*1000 if started else 0.
    return result


def selection_for_detection(found, shape, margin=.08):
    """Fractional selection around a detection (its upright bounds + margin)."""
    h, w = shape[:2]
    x1, y1, x2, y2 = found['box']
    mx, my = margin*(x2-x1), margin*(y2-y1)
    return (max(0., (x1-mx)/w), max(0., (y1-my)/h), min(1., (x2+mx)/w), min(1., (y2+my)/h))


def canvas_to_source(points, pad, scale):
    """Letterbox-canvas points -> source-image pixels (0.8.8: one mapping for
    the box/OBB and segment decoders, which differed by up to a pixel).

    The letterbox gain is uniform, as in Ultralytics' own post-processing, so
    rotated rectangles stay rectangles; the rounding of the resized size is
    below half a canvas pixel."""
    return (np.asarray(points, np.float64) - [pad[0], pad[1]]) / scale


def clip_to_source(points, shape):
    """Clip pixel coordinates to the source image, [0, w-1] x [0, h-1]."""
    h, w = shape[:2]
    points = np.array(points, copy=True)
    points[:, 0] = points[:, 0].clip(0, w-1)
    points[:, 1] = points[:, 1].clip(0, h-1)
    return points


class ICDetector:
    def __init__(self, model=None, spec=None, device='auto'):
        import onnxruntime as ort
        model = Path(model) if model else default_model()
        spec = Path(spec) if spec else model.with_suffix('.json')
        self.inference_lock = threading.Lock()
        self.cached = None
        self.spec = json.loads(spec.read_text('utf-8')) if spec.exists() else {}
        self.input_name = self.spec.get('input_name', 'images')
        shape = self.spec.get('input_shape', [1, 3, 640, 640])
        self.size = (int(shape[3]), int(shape[2]))   # width, height
        self.confidence = float(self.spec.get('suggested_confidence', .35))
        self.iou = float(self.spec.get('suggested_nms_iou', .45))
        import os
        self.native_preprocessing = os.environ.get('ICOCR_DETECTOR_ALIGNMENT', '1') != '0'
        self.classes = self.spec.get('classes', ['ic_body'])
        channels = self.spec.get('channels', [])
        # Rotated-box (OBB) exports add an angle channel after the class scores.
        self.segmented = self.spec.get('task') == 'segment'
        self.oriented = (self.spec.get('task') == 'obb' or any('angle' in c for c in channels))
        import os
        device = (device if device != 'auto' else os.environ.get('ICLENS_DEVICE', 'auto')).lower()
        providers = ['CPUExecutionProvider']
        if device != 'cpu' and 'CUDAExecutionProvider' in ort.get_available_providers():
            try:
                from ocr_runtime import prepare_cuda_dlls, cuda_provider
                prepare_cuda_dlls(ort)
                providers.insert(0, cuda_provider())
            except Exception:
                logging.exception('CUDA unavailable for the IC detector; using CPU')
        options = ort.SessionOptions()
        from ocr_runtime import thread_count, configure_session_options
        options.intra_op_num_threads = thread_count(2)   # OCR shares the CPU
        configure_session_options(options)
        self.session = ort.InferenceSession(str(model), options, providers=providers)
        self.providers = self.session.get_providers()
        self.name = model.name
        metadata = self.session.get_modelmeta().custom_metadata_map
        model_task = metadata.get('task', '')
        declared = self.spec.get('task')
        if declared and model_task and declared != model_task:
            raise ValueError(f'{model.name}: JSON task {declared!r} conflicts with ONNX task {model_task!r}')
        self.task = declared or model_task or ('obb' if self.oriented else 'detect')
        if self.task not in ('detect','obb','segment'):
            raise ValueError(f'{model.name}: unsupported detector task {self.task!r}')
        self.oriented, self.segmented = self.task == 'obb', self.task == 'segment'
        if not isinstance(self.classes,list) or not self.classes:
            raise ValueError('Detector JSON classes must be a non-empty list')
        if self.segmented and self.classes != ['ic_body']:
            raise ValueError('Segmentation currently requires the single ic_body class')
        self.output_shapes = [list(o.shape) for o in self.session.get_outputs()]
        predictions = [i for i, shape in enumerate(self.output_shapes) if len(shape)==3]
        prototypes = [i for i, shape in enumerate(self.output_shapes) if len(shape)==4]
        if len(predictions)!=1 or (self.segmented and len(prototypes)!=1):
            raise ValueError(f'{model.name}: expected raw YOLO predictions [1,C,N]' +
                             (' and mask prototypes [1,M,H,W]' if self.segmented else '') +
                             '; export ONNX with nms=False')
        self.prediction_index = predictions[0]
        self.prototype_index = prototypes[0] if self.segmented else None
        self.mask_channels = self.output_shapes[self.prototype_index][1] if self.segmented else 0
        if self.segmented and (not isinstance(self.mask_channels,int) or self.mask_channels<=0):
            raise ValueError('Segmentation requires a static CHW mask prototype output')
        expected = 4 + len(self.classes) + (1 if self.oriented else self.mask_channels)
        channels_out = self.output_shapes[self.prediction_index][1]
        if isinstance(channels_out, int) and channels_out != expected:
            raise ValueError(f'{model.name}: output has {channels_out} channels, expected {expected} '
                             f'({self.task}, {len(self.classes)} classes). Check the .json beside the model.')
        inputs = self.session.get_inputs()
        if len(inputs)!=1 or len(inputs[0].shape)!=4:
            raise ValueError('Expected one NCHW image input')
        inp=inputs[0]
        if self.spec.get('input_name') and self.spec['input_name']!=inp.name:
            raise ValueError('JSON input_name does not match ONNX input')
        self.input_name=inp.name
        if all(isinstance(v,int) for v in inp.shape):
            if inp.shape[:2]!=[1,3]:raise ValueError('Expected batch-one RGB input')
            actual=(inp.shape[3],inp.shape[2])
            if 'input_shape' in self.spec and actual!=self.size:
                raise ValueError('JSON input_shape does not match ONNX input')
            self.size=actual
        self.max_detections=100

    def letterbox(self, image, native_preprocessing=None):
        h, w = image.shape[:2]
        native = getattr(self, 'native_preprocessing', True) if native_preprocessing is None else native_preprocessing
        tw, th = self.size
        scale = min(tw/w, th/h)
        nw, nh = max(1, round(w*scale)), max(1, round(h*scale))
        resized = cv2.resize(image, (nw, nh), interpolation=(cv2.INTER_LINEAR if native or scale >= 1 else cv2.INTER_AREA))
        pad_x, pad_y = (tw-nw)//2, (th-nh)//2
        canvas = np.full((th, tw, 3), 114, np.uint8)
        canvas[pad_y:pad_y+nh, pad_x:pad_x+nw] = resized
        return canvas, scale, pad_x, pad_y

    def detect(self, image, confidence=None, *, native_preprocessing=None):
        """All IC bodies in a BGR image, best first.

        Each result: box=[x1,y1,x2,y2] (upright bounds), polygon=4 corners,
        score, and angle (degrees; 0 for upright models).
        """
        h, w = image.shape[:2]
        canvas, scale, pad_x, pad_y = self.letterbox(image, native_preprocessing)
        # One contiguous NCHW RGB float32 pass (same values as
        # cvtColor+astype+transpose, then the same division by 255).
        blob = cv2.dnn.blobFromImage(canvas, 1.0, swapRB=True)
        blob /= 255.
        outputs = self.session.run(None, {self.input_name: blob})
        if getattr(self, 'segmented', False):
            return self._decode_segment(outputs, image.shape, scale, pad_x, pad_y, confidence)
        output = outputs[getattr(self, 'prediction_index', 0)][0]   # (channels, N)
        count = len(self.classes)
        # Score channels only: an OBB export appends the angle after the class scores.
        scores = output[4:4+count].max(axis=0)
        keep = scores >= (self.confidence if confidence is None else confidence)
        if not np.any(keep):
            return []
        cx, cy, bw, bh = output[:4, keep]
        scores = scores[keep]
        if self.oriented:
            angles = output[4+count, keep]
            rects = [((float(x), float(y)), (float(a), float(b)), float(np.degrees(t)))
                     for x, y, a, b, t in zip(cx, cy, bw, bh, angles)]
            chosen = cv2.dnn.NMSBoxesRotated(rects, scores.astype(float).tolist(), 0., self.iou)
        else:
            angles = np.zeros_like(cx)
            rects = [[float(x-a/2), float(y-b/2), float(a), float(b)] for x, y, a, b in zip(cx, cy, bw, bh)]
            chosen = cv2.dnn.NMSBoxes(rects, scores.astype(float).tolist(), 0., self.iou)
        found = []
        for i in np.asarray(chosen).reshape(-1):
            cos, sin = np.cos(angles[i]), np.sin(angles[i])
            v1 = np.array([bw[i]/2*cos, bw[i]/2*sin])
            v2 = np.array([-bh[i]/2*sin, bh[i]/2*cos])
            centre = np.array([cx[i], cy[i]])
            corners = np.array([centre+v1+v2, centre+v1-v2, centre-v1-v2, centre-v1+v2])
            corners = canvas_to_source(corners, (pad_x, pad_y), scale)
            truncated = bool(np.any(corners < -1) or np.any(corners[:, 0] > w+1) or
                             np.any(corners[:, 1] > h+1))
            corners = clip_to_source(corners, (h, w))
            found.append(dict(box=[float(corners[:, 0].min()), float(corners[:, 1].min()),
                                   float(corners[:, 0].max()), float(corners[:, 1].max())],
                              polygon=corners.tolist(), score=float(scores[i]),
                              angle=float(np.degrees(angles[i])), truncated=truncated))
        return sorted(found, key=lambda d: d['score'], reverse=True)

    def _decode_segment(self, outputs, shape, scale, pad_x, pad_y, confidence=None):
        """Decode masks after box NMS; bound work and never treat coefficients as scores.

        Logits > 0 equals sigmoid(logits) > 0.5. Upsample at model resolution,
        crop to the candidate box and valid image, then map contours to source.
        Keep a convex mask outline for masking and a quad for existing OCR geometry.
        """
        h,w=shape[:2];tw,th=self.size
        pred=np.asarray(outputs[self.prediction_index])
        proto=np.asarray(outputs[self.prototype_index])
        count=len(self.classes);expected=4+count+self.mask_channels
        if pred.ndim!=3 or pred.shape[0]!=1 or pred.shape[1]!=expected:
            raise ValueError(f'Invalid segmentation predictions: {pred.shape}, expected [1,{expected},N]')
        if proto.ndim!=4 or proto.shape[:2]!=(1,self.mask_channels) or min(proto.shape[2:])<1:
            raise ValueError(f'Invalid segmentation prototypes: {proto.shape}')
        if not np.isfinite(proto).all():raise ValueError('Non-finite mask prototypes')
        pred=pred[0];proto=proto[0].astype(np.float32,copy=False)
        scores=pred[4:4+count].max(axis=0)
        threshold=self.confidence if confidence is None else confidence
        ids=np.flatnonzero((scores>=threshold)&np.isfinite(pred).all(axis=0)&(pred[2]>0)&(pred[3]>0))
        ids=ids[np.argsort(-scores[ids],kind='stable')[:3000]]
        if not len(ids):return []
        candidates=pred[:,ids];scores=scores[ids]
        rects=[[float(x-a/2),float(y-b/2),float(a),float(b)] for x,y,a,b in candidates[:4].T]
        chosen=np.asarray(cv2.dnn.NMSBoxes(rects,scores.astype(float).tolist(),0.,self.iou)).reshape(-1)
        chosen=sorted(chosen,key=lambda i:float(scores[i]),reverse=True)[:self.max_detections]
        mh,mw=proto.shape[1:];flat=proto.reshape(self.mask_channels,-1)
        nw,nh=max(1,round(w*scale)),max(1,round(h*scale))
        # 0.8.4.3: with a power-of-two upsampling factor (640/160 = 4) only the
        # prototype window under the box is combined and upsampled. Bilinear
        # weights depend only on the position within a factor-sized cell, so
        # the window's values equal the full-canvas values (tests compare).
        fx,fy=tw//mw,th//mh
        windowed=(getattr(self,'windowed_masks',True) and fx*mw==tw and fy*mh==th and fx>=1 and fy>=1 and
                  not fx&(fx-1) and not fy&(fy-1))
        found=[]
        for i in chosen:
            x,y,bw,bh=rects[i]
            # Integer pixel locations matching Ultralytics crop_mask comparisons.
            left=max(pad_x,int(np.ceil(x)),0);top=max(pad_y,int(np.ceil(y)),0)
            right=min(pad_x+nw,int(np.ceil(x+bw)),tw);bottom=min(pad_y+nh,int(np.ceil(y+bh)),th)
            if right-left<2 or bottom-top<2:continue
            coefficients=candidates[4+count:,i].astype(np.float32)
            logits=(coefficients@flat).reshape(mh,mw)
            if windowed:
                contours=self._window_contours(logits,(fx,fy),(left,top,right,bottom),(tw,th))
            else:
                logits=cv2.resize(logits,(tw,th),interpolation=cv2.INTER_LINEAR)
                mask=(logits>0).astype(np.uint8)
                mask[:top]=0;mask[bottom:]=0;mask[:,:left]=0;mask[:,right:]=0
                contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            if not contours:continue
            contour=max(contours,key=cv2.contourArea)
            if cv2.contourArea(contour)<4:continue
            pts=contour.reshape(-1,2).astype(np.float32)
            touches=bool(np.any(pts[:,0]<=pad_x+1) or np.any(pts[:,0]>=pad_x+nw-2) or
                         np.any(pts[:,1]<=pad_y+1) or np.any(pts[:,1]>=pad_y+nh-2))
            pts=canvas_to_source(pts,(pad_x,pad_y),scale).astype(np.float32)
            hull=cv2.convexHull(pts.astype(np.float32))
            perimeter=cv2.arcLength(hull,True);area=cv2.contourArea(hull)
            quad=None;fit='minimum-area rectangle'
            for fraction in (.005,.01,.015,.02,.025,.03,.04):
                approx=cv2.approxPolyDP(hull,fraction*perimeter,True)
                if len(approx)==4 and cv2.isContourConvex(approx) and cv2.contourArea(approx)>=.85*area:
                    quad=approx.reshape(4,2);fit='perspective quad';break
            if quad is None:quad=cv2.boxPoints(cv2.minAreaRect(hull))
            # Reject geometry outside source instead of clipping a fitted rectangle into a false quad.
            touches=touches or bool(np.any(quad<0) or np.any(quad[:,0]>w-1) or np.any(quad[:,1]>h-1))
            quad=clip_to_source(quad,(h,w))
            outline=cv2.approxPolyDP(hull,.002*perimeter,True).reshape(-1,2)
            bounds=np.vstack((outline,quad))
            edge=quad[1]-quad[0]
            found.append(dict(box=[float(bounds[:,0].min()),float(bounds[:,1].min()),
                                   float(bounds[:,0].max()),float(bounds[:,1].max())],
                polygon=quad.tolist(),mask_polygon=outline.tolist(),score=float(scores[i]),
                angle=float(np.degrees(np.arctan2(edge[1],edge[0]))),truncated=touches,
                task='segment',geometry=fit,mask_area=float(area),mask_threshold=.5))
        return found

    @staticmethod
    def _window_contours(logits, factors, box, canvas):
        """Contours of (upsampled logits > 0) inside box, as on the full canvas.

        The prototype window keeps one source cell of margin so every output
        pixel inside the box has the same two bilinear neighbours as in the
        full-canvas resize. The mask keeps a one-pixel zero ring (or the true
        canvas edge), because findContours ignores an image's outer pixels.
        """
        fx, fy = factors
        left, top, right, bottom = box
        tw, th = canvas
        mh, mw = logits.shape
        sx0, sx1 = max(0, left//fx-1), min(mw, (right-1)//fx+2)
        sy0, sy1 = max(0, top//fy-1), min(mh, (bottom-1)//fy+2)
        window = cv2.resize(np.ascontiguousarray(logits[sy0:sy1, sx0:sx1]),
                            ((sx1-sx0)*fx, (sy1-sy0)*fy), interpolation=cv2.INTER_LINEAR)
        ox, oy = sx0*fx, sy0*fy                       # window origin on the canvas
        rx0, ry0 = max(0, left-1), max(0, top-1)       # region with a zero ring
        rx1, ry1 = min(tw, right+1), min(th, bottom+1)
        mask = np.zeros((ry1-ry0, rx1-rx0), np.uint8)
        mask[top-ry0:bottom-ry0, left-rx0:right-rx0] = (
            window[top-oy:bottom-oy, left-ox:right-ox] > 0)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
                                       offset=(rx0, ry0))
        return contours

    def detect_cached(self, image, *, native_preprocessing=None, max_age=.75):
        """Share serialized inference between preview and OCR, on stable views.

        The cache reference remains the inferred frame, never a rolling frame.
        Model/preprocessing/shape changes and expiry force a new inference.
        """
        from frame_guard import signature, stationary
        import copy
        started = time.perf_counter()
        native = self.native_preprocessing if native_preprocessing is None else native_preprocessing
        stamp = signature(image)
        with self.inference_lock:
            now = time.monotonic()
            old = self.cached
            if (old and old['shape'] == image.shape and old['native'] == native and
                    now - old['created'] <= max_age and stationary(old['signature'], stamp)):
                return copy.deepcopy(old['found']), dict(cache_hit=True,
                    cache_age_ms=(now-old['created'])*1000,
                    milliseconds=(time.perf_counter()-started)*1000)
            found = self.detect(image, native_preprocessing=native)
            self.cached = dict(shape=image.shape, native=native, signature=stamp,
                               created=time.monotonic(), found=copy.deepcopy(found))
            return found, dict(cache_hit=False, cache_age_ms=0.,
                               milliseconds=(time.perf_counter()-started)*1000)

    def locate(self, image):
        """locate_body-compatible result for one user selection.

        Picks the detection nearest the selection centre (weighted by score).
        Bodies cut off by the selection edge are not used for cropping (the OCR
        would lose characters); the reason says so and the full selection is used.
        """
        started = time.perf_counter()
        result = dict(status='fallback', reason='Model found no IC body', box=None, score=0.,
                      source='model', detections=[])
        try:
            found = self.detect(image)
        except Exception as exc:
            logging.exception('IC detector failed')
            result.update(reason='IC detector error: '+str(exc))
            found = []
        h, w = image.shape[:2]
        result['detections'] = found
        if found:
            def preference(d):
                x1, y1, x2, y2 = d['box']
                distance = np.hypot(((x1+x2)/2-w/2)/w, ((y1+y2)/2-h/2)/h)
                return d['score'] - .5*distance
            best = max(found, key=preference)
            x1, y1, x2, y2 = best['box']
            clipped = best.get('truncated') or x1 <= 1 or y1 <= 1 or x2 >= w-1 or y2 >= h-1
            if min(x2-x1, y2-y1) < 12:
                result['reason'] = 'Model body too small'
            elif clipped and (self.oriented or getattr(self,'segmented',False)):
                result.update(reason='Model IC body touches selection edge', score=best['score'],
                               candidate_count=len(found))
            else:
                result.update(status='detected', score=best['score'], box=best['polygon'],
                              angle=best.get('angle', 0.), candidate_count=len(found),
                              reason=('Model IC body (touches selection edge)' if clipped
                                      else 'Model IC body'))
        if result['status']=='detected' and found and best.get('mask_polygon'):
            result.update(mask_polygon=best['mask_polygon'],task='segment',geometry=best['geometry'])
        result['milliseconds'] = (time.perf_counter()-started)*1000
        return result


_detectors = {}
_detector_lock = threading.Lock()


def shared_detector(model=None):
    """One session per model path, shared by the overlay and OCR worker."""
    path = Path(model or default_model()).resolve()
    try:
        stat = path.stat()
        spec = path.with_suffix('.json')
        stamp = (stat.st_mtime_ns, stat.st_size, spec.stat().st_mtime_ns if spec.exists() else None)
    except OSError:
        stamp = None
    key = (str(path), stamp)
    with _detector_lock:
        if key not in _detectors:
            try:
                _detectors[key] = (ICDetector(path), '')
            except Exception as exc:
                logging.exception('IC detector unavailable')
                _detectors[key] = (None, str(exc))
        while len(_detectors) > 4:
            del _detectors[next(iter(_detectors))]
        return _detectors[key]


def forget_failed_detector(model=None):
    """Drop cached load failures for ``model`` so the next request retries (0.8.8)."""
    path = str(Path(model or default_model()).resolve())
    with _detector_lock:
        for key in [key for key, (detector, _) in _detectors.items() if key[0] == path and detector is None]:
            del _detectors[key]


class _KnownLoadFailure(Exception):
    """A detector load that already failed for this model/generation."""


class DetectionWorker:
    """Latest-frame mailbox: the detector runs on the newest frame only, at most
    every `interval` seconds, so it never queues behind the camera or the OCR."""

    def __init__(self, interval=.15, factory=None):
        import threading
        self.interval = interval
        self.factory = factory or (lambda path: shared_detector(path)[0])
        self.condition = threading.Condition()
        self.pending = None
        self.result = None
        self.detector = None
        self.model_path = None
        self.generation = 0
        import os
        self.native_preprocessing = os.environ.get('ICOCR_DETECTOR_ALIGNMENT', '1') != '0'
        self.error = ''
        # (model_path, generation, message) of the last failed load: reported on
        # every frame but not retried or re-logged until load() or a new generation.
        self._load_failure = None
        self._forget_shared_failure = False
        self.closed = False
        self.paused = False
        self.thread = threading.Thread(target=self._run, name='detector', daemon=True)
        self.thread.start()

    def load(self, path=None):
        """Use another model file (e.g. a newly trained export). Errors are reported."""
        with self.condition:
            self.model_path = str(Path(path).resolve()) if path else None
            self.generation += 1
            self.detector = None
            self.error = ''
            self._load_failure = None
            self._forget_shared_failure = True   # done on the worker thread, off the UI
            self.result = None
            self.condition.notify_all()

    def configure_preprocessing(self, enabled):
        with self.condition:
            self.native_preprocessing = bool(enabled)
            self.generation += 1
            self.result = None
            self.condition.notify_all()

    def discard_results(self):
        """Sleep invalidation: reject an inference already in flight."""
        with self.condition:
            self.generation += 1
            self.pending = self.result = None
            self.condition.notify_all()

    def set_paused(self, paused):
        with self.condition:
            self.paused = bool(paused)
            if self.paused:
                self.pending = None
            self.condition.notify_all()

    def submit(self, frame_id, frame):
        with self.condition:
            if not self.closed and not self.paused:
                self.pending = (frame_id, frame)
                self.condition.notify()

    def latest(self):
        with self.condition:
            return self.result

    def close(self):
        with self.condition:
            self.closed = True
            self.condition.notify()
        self.thread.join(timeout=2)

    def _run(self):
        last = 0.
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.closed or (not self.paused and self.pending is not None))
                if self.closed:
                    return
                # Wait before taking the mailbox, so frames arriving during the
                # throttle interval replace the old frame. Close interrupts wait.
                while not self.closed:
                    wait = self.interval - (time.monotonic() - last)
                    if wait <= 0:
                        break
                    self.condition.wait(timeout=wait)
                if self.closed:
                    return
                if self.paused or self.pending is None:
                    continue
                frame_id, frame = self.pending
                self.pending = None
                path, detector = self.model_path, self.detector
                generation = self.generation
                native = self.native_preprocessing
                failure = self._load_failure
                if failure is not None and failure[:2] != (path, generation):
                    failure = None
                forget, self._forget_shared_failure = self._forget_shared_failure, False
            loading = False
            try:
                if detector is None:
                    if failure is not None:
                        raise _KnownLoadFailure(failure[2])
                    loading = True
                    if forget:
                        forget_failed_detector(path)
                    detector = self.factory(path)
                    if detector is None:
                        raise RuntimeError(shared_detector(path)[1] or 'Detector model unavailable')
                    loading = False
                    with self.condition:
                        if self.generation == generation:
                            self.detector = detector
                started = time.perf_counter()
                if callable(getattr(type(detector), 'detect_cached', None)):
                    found, timing = detector.detect_cached(frame, native_preprocessing=native)
                else:
                    found = detector.detect(frame, native_preprocessing=native)
                    timing = dict(cache_hit=False, cache_age_ms=0.)
                result = dict(frame_id=frame_id, frame=frame, completed=time.monotonic(),
                              native_preprocessing=native,
                              cache_hit=timing['cache_hit'], cache_age_ms=timing['cache_age_ms'],
                              shape=frame.shape[:2], detections=found,
                              milliseconds=(time.perf_counter()-started)*1000,
                              model=detector.name, model_path=path, providers=detector.providers, error='')
            except _KnownLoadFailure as exc:
                result = dict(frame_id=frame_id, shape=frame.shape[:2], detections=[],
                              milliseconds=0., model=path or 'ic_body.onnx', model_path=path, providers=[],
                              error=str(exc))
            except Exception as exc:
                if loading:
                    # Log once; later frames reuse the cached error until load().
                    logging.exception('Chip detector could not be loaded')
                    with self.condition:
                        if self.generation == generation:
                            self._load_failure = (path, generation, str(exc))
                else:
                    logging.exception('Chip detector failed')
                result = dict(frame_id=frame_id, shape=frame.shape[:2], detections=[],
                              milliseconds=0., model=path or 'ic_body.onnx', model_path=path, providers=[],
                              error=str(exc))
            last = time.monotonic()
            with self.condition:
                if self.generation == generation:
                    self.result = result
