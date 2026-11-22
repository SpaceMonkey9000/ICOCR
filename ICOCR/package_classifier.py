"""ICTRAIN whole-package classifier. Advisory evidence; never filters OCR or DB hits."""
import hashlib
import ast
import json
import logging
import threading
import time
from pathlib import Path

import numpy as np
from PIL import Image

from project_paths import DATA

PREPROCESSING = 'package_letterbox_v1'
_lock = threading.Lock()
_key = None
_classifier = None
_error = None


def default_model():
    """Runtime weights always belong to the same shared DATA as other models."""
    return DATA/'models'/'package_classifier.onnx'


def contract(model):
    model = Path(model)
    meta = json.loads(model.with_suffix('.json').read_text(encoding='utf-8'))
    classes = meta.get('classes')
    if (meta.get('kind') != 'package_classification' or meta.get('task') != 'classify'
            or meta.get('preprocessing') != PREPROCESSING
            or meta.get('input_shape') != [1, 3, 224, 224]
            or not isinstance(classes, list) or len(classes) < 2
            or any(not isinstance(c, str) or not c.strip() for c in classes)
            or len(set(classes)) != len(classes)
            or meta.get('output_shape') != [1, len(classes)]):
        raise ValueError('Unsupported ICTRAIN package classifier contract')
    if hashlib.sha256(model.read_bytes()).hexdigest() != meta.get('sha256'):
        raise ValueError('Package classifier checksum mismatch')
    return meta


def input_array(bgr):
    """Exact ICTRAIN Pillow bilinear preprocessing, including rounding and RGB."""
    if bgr.ndim != 3 or bgr.shape[2] != 3 or min(bgr.shape[:2]) < 1:
        raise ValueError('Expected a non-empty BGR image')
    image = Image.fromarray(np.ascontiguousarray(bgr[..., ::-1]))
    inner = round(224*.9)
    scale = inner/max(image.size)
    dims = tuple(max(1, round(v*scale)) for v in image.size)
    image = image.resize(dims, Image.Resampling.BILINEAR)
    canvas = Image.new('RGB', (224, 224), (114, 114, 114))
    canvas.paste(image, ((224-dims[0])//2, (224-dims[1])//2))
    return (np.asarray(canvas, dtype=np.float32).transpose(2, 0, 1).copy()/255.)[None]


class PackageClassifier:
    def __init__(self, model):
        import onnxruntime as ort
        self.path = Path(model)
        self.meta = contract(self.path)
        self.classes = self.meta['classes']
        # This tiny, once-per-scan model shares the CPU without GPU setup latency.
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        self.session = ort.InferenceSession(str(self.path), options, providers=['CPUExecutionProvider'])
        embedded = self.session.get_modelmeta().custom_metadata_map
        if embedded.get('task', 'classify') != 'classify':
            raise ValueError('Package ONNX is not a classifier')
        if 'names' in embedded:
            names = ast.literal_eval(embedded['names'])
            ordered = [names[i] for i in range(len(names))] if isinstance(names, dict) else names
            if ordered != self.classes:
                raise ValueError('Package ONNX class order differs from JSON')
        inputs, outputs = self.session.get_inputs(), self.session.get_outputs()
        if (len(inputs) != 1 or inputs[0].shape != [1, 3, 224, 224]
                or inputs[0].type != 'tensor(float)' or len(outputs) != 1
                or outputs[0].shape != [1, len(self.classes)]
                or inputs[0].name != self.meta.get('input_name')):
            raise ValueError('Package ONNX shape or input name differs from JSON')
        self.input_name = inputs[0].name

    def predict(self, image, threshold=.5):
        values = np.asarray(self.session.run(None, {self.input_name: input_array(image)})[0])
        if (values.shape != (1, len(self.classes)) or not np.isfinite(values).all()
                or np.any(values < 0) or np.any(values > 1)
                or not np.isclose(values.sum(), 1., atol=1e-4)):
            raise ValueError('Invalid package probabilities')
        values = values[0]
        indices = np.argsort(-values)
        best = int(indices[0])
        score = float(values[best])
        return dict(status='classified' if score >= threshold else 'unknown',
                    package=self.classes[best] if score >= threshold else 'unknown',
                    best_class=self.classes[best], confidence=score, threshold=threshold,
                    candidates=[dict(package=self.classes[int(i)], confidence=float(values[i]))
                                for i in indices], model=self.path.name, advisory=True)


def _signature(model):
    paths = (model, model.with_suffix('.json'))
    return tuple((str(p.resolve()), p.stat().st_mtime_ns, p.stat().st_size)
                 if p.exists() else (str(p.resolve()), None, None) for p in paths)


def shared_classifier(model):
    global _key, _classifier, _error
    with _lock:
        key = _signature(model)
        if key != _key:
            _key, _classifier, _error = key, None, None
            try:
                _classifier = PackageClassifier(model)
            except Exception as exc:
                _error = str(exc)
                logging.warning('Package classifier unavailable: %s', exc)
        return _classifier, _error


def classify_region(image, detection=None, options=None):
    """Classify original pixels with context for leads, never the OCR body mask.

    A detected body gets 25% padding per side, clipped to the selection. Without
    a body the user's single-package selection is used as supplied.
    """
    options = options or {}
    if not options.get('enabled', False):
        return dict(status='disabled', package='unknown', advisory=True, milliseconds=0.)
    started = time.perf_counter()
    try:
        threshold = float(options.get('confidence', .5))
        if not np.isfinite(threshold) or not 0 <= threshold <= 1:
            raise ValueError('Package confidence must be between 0 and 1')
        model = Path(options.get('model') or default_model())
        classifier, error = shared_classifier(model)
        if classifier is None:
            return dict(status='unavailable', package='unknown', reason=error, advisory=True,
                        milliseconds=(time.perf_counter()-started)*1000)
        h, w = image.shape[:2]
        bounds = [0, 0, w, h]
        box = (detection or {}).get('box')
        source = 'selection'
        if box is not None and (detection or {}).get('status') in ('detected', 'applied'):
            points = np.asarray(box, float).reshape(-1, 2)
            if not np.isfinite(points).all():
                raise ValueError('Invalid package body coordinates')
            lo, hi = points.min(axis=0), points.max(axis=0)
            margin = (hi-lo)*.25
            left, top = np.maximum(0, np.floor(lo-margin)).astype(int)
            right, bottom = np.minimum([w, h], np.ceil(hi+margin)).astype(int)
            bounds = [int(left), int(top), int(right), int(bottom)]
            source = 'padded body bounds'
        left, top, right, bottom = bounds
        if right-left < 12 or bottom-top < 12:
            raise ValueError('Package crop is too small')
        result = classifier.predict(image[top:bottom, left:right], threshold)
        result.update(crop_bounds=bounds, crop_source=source,
                      milliseconds=(time.perf_counter()-started)*1000)
        return result
    except Exception as exc:
        logging.warning('Package classification failed: %s', exc)
        return dict(status='error', package='unknown', reason=str(exc), advisory=True,
                    milliseconds=(time.perf_counter()-started)*1000)


def summary(result):
    result = result or {}
    if result.get('status') == 'classified':
        return f"Package: {result['package']} ({result['confidence']:.0%})"
    if result.get('status') == 'unknown':
        return f"Package: unknown (best {result['best_class']}, {result['confidence']:.0%})"
    return 'Package: ' + result.get('status', 'not scanned')


def classify_scan(image, detection, options, frame=None, roi=None):
    """Use full-frame context for leads when a body is known, without widening OCR."""
    try:
        mapped = detection
        space = 'selection'
        if (frame is not None and roi is not None and (detection or {}).get('box') is not None
                and detection.get('status') in ('detected', 'applied')):
            h, w = frame.shape[:2]
            origin = [max(0, min(w-1, int(roi[0]*w))), max(0, min(h-1, int(roi[1]*h)))]
            mapped = dict(detection, box=(np.asarray(detection['box'])+origin).tolist())
            image, space = frame, 'frame'
        result = classify_region(image, mapped, options)
        result['crop_space'] = space
        return result
    except Exception as exc:
        logging.warning('Package context failed: %s', exc)
        return dict(status='error', package='unknown', reason=str(exc), advisory=True, milliseconds=0.)
