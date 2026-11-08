"""Versioned, geometry-preserving preprocessing shared by ICOCR and ICBENCH.

Imports are lazy so the benchmark launcher needs only the standard library.
Gamma uses output = 255 * (input / 255) ** gamma; gamma < 1 brightens.
"""
from contextlib import contextmanager
import math

VERSION = '1.0.0'
PRESETS = ('Original', 'Local contrast', 'Illumination', 'Gamma', 'Invert',
           'Lighting correction', 'Sharpen', 'Threshold')
INITIAL_PRESETS = PRESETS[:5]
DEFAULT_SETTINGS = {'gamma': 0.65, 'background_sigma': 21.0,
                    'clahe_clip': 2.0, 'clahe_grid': 8}


def settings(values=None):
    result = dict(DEFAULT_SETTINGS)
    values = values or {}
    if set(values) - set(result):
        raise ValueError('Unknown preprocessing settings: ' + str(sorted(set(values)-set(result))))
    result.update(values)
    for key in result:
        value = float(result[key])
        if not math.isfinite(value):
            raise ValueError('Non-finite preprocessing setting: ' + key)
        result[key] = value
    for key, low, high in [('gamma', .1, 5), ('background_sigma', 1, 200),
                           ('clahe_clip', .1, 20), ('clahe_grid', 2, 32)]:
        if not low <= result[key] <= high:
            raise ValueError(f'{key} must be between {low} and {high}')
    if not result['clahe_grid'].is_integer():
        raise ValueError('clahe_grid must be an integer')
    result['clahe_grid'] = int(result['clahe_grid'])
    return result


def configuration(config):
    """Normalize a bounded explicit policy; None is the unchanged legacy policy."""
    if config is None:
        return None
    if set(config) - {'mode', 'presets', 'stage', 'settings'}:
        raise ValueError('Unknown preprocessing configuration field')
    mode = config.get('mode', 'single')
    stage = config.get('stage', 'snapshot')
    presets = config.get('presets', ['Original'])
    if mode not in ('single', 'fallback') or stage not in ('snapshot', 'crop'):
        raise ValueError('Invalid preprocessing mode or stage')
    if not isinstance(presets, (tuple, list)) or not 1 <= len(presets) <= 5:
        raise ValueError('Choose between one and five preprocessing presets')
    if any(p not in PRESETS for p in presets) or len(set(presets)) != len(presets):
        raise ValueError('Unknown or duplicate preprocessing preset')
    if mode == 'single' and len(presets) != 1:
        raise ValueError('Single-preset mode requires exactly one preset')
    return dict(mode=mode, stage=stage, presets=list(presets), settings=settings(config.get('settings')))


def preprocess(image, preset='Original', values=None):
    import cv2
    import numpy as np
    opts = settings(values)
    if preset not in PRESETS:
        raise ValueError('Unknown processing mode: ' + str(preset))
    if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3 or not image.size:
        raise ValueError('Preprocessing requires a nonempty uint8 BGR image')
    if preset == 'Original':
        return image.copy()
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if preset in ('Illumination', 'Lighting correction'):
        background = cv2.GaussianBlur(gray, (0, 0), opts['background_sigma'])
        gray = cv2.divide(gray, np.maximum(background, 1), scale=128)
    if preset in ('Local contrast', 'Lighting correction'):
        gray = cv2.createCLAHE(clipLimit=opts['clahe_clip'],
                              tileGridSize=(opts['clahe_grid'],)*2).apply(gray)
    elif preset == 'Gamma':
        lut = np.rint(255 * (np.arange(256)/255.) ** opts['gamma']).astype(np.uint8)
        gray = cv2.LUT(gray, lut)
    elif preset == 'Invert':
        gray = 255-gray
    elif preset == 'Sharpen':
        blur = cv2.GaussianBlur(gray, (0, 0), 1.2)
        gray = cv2.addWeighted(gray, 1.6, blur, -.6, 0)
    elif preset == 'Threshold':
        gray = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY, 31, 7)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


def accepted(decision, has_catalog):
    """Label-blind stopping rule. A database hit is not proof of correctness."""
    row = decision.get('selected') or {}
    if not row or row.get('provisional'):
        return False
    if row.get('conflicts') and not row.get('database_identity_consistent'):
        return False
    if has_catalog:
        return bool(row.get('selected_database_match'))
    return row.get('score', 0) >= .90


class CropRecognizer:
    def __init__(self, original, preset, values):
        self.original, self.preset, self.values = original, preset, values
    def __getattr__(self, name):
        return getattr(self.original, name)
    def __call__(self, crops, *args, **kwargs):
        return self.original([preprocess(c, self.preset, self.values) for c in crops], *args, **kwargs)


@contextmanager
def recognition_preprocessing(engine, preset, values, enabled):
    # Unwrap diagnostic proxies so both engine.__call__ and explicit fast-path
    # text_rec calls see the same transform; restore even when inference fails.
    target = engine
    while hasattr(target, '__dict__') and 'engine' in vars(target):
        target = target.engine
    original = target.text_rec
    if enabled:
        target.text_rec = CropRecognizer(original, preset, values)
    try:
        yield
    finally:
        if enabled:
            target.text_rec = original
