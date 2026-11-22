"""Preview-only focus aid. Never modifies camera frames or OCR input.

Fixed thresholds deliberately do not normalize each frame: defocusing should
remove highlights, rather than promote the strongest remaining blurry edge.
"""
import cv2
import numpy as np

COLOURS = {'Red': (0, 0, 255), 'Green': (0, 255, 0),
           'Yellow': (0, 255, 255), 'Cyan': (255, 255, 0)}  # BGR
SENSITIVITIES = {'Low': 32., 'Medium': 18., 'High': 9.}
OPACITIES = {'50%': .5, '75%': .75, '100%': 1.}
DEFAULTS = {'peaking_colour': 'Red', 'peaking_sensitivity': 'Medium',
            'peaking_opacity': '75%'}
CHOICES = {'peaking_colour': COLOURS, 'peaking_sensitivity': SENSITIVITIES,
           'peaking_opacity': OPACITIES}


def options(preferences):
    """Validate persisted choices; tolerate missing or malformed old settings."""
    return {name: preferences.get(name) if isinstance(preferences.get(name), str)
            and preferences[name] in CHOICES[name] else default
            for name, default in DEFAULTS.items()}


def overlay(preview, colour='Red', sensitivity='Medium', opacity='75%'):
    """Return a BGR copy with fine edges highlighted at preview resolution.

    A small Gaussian suppresses single-pixel noise before the Laplacian picks
    out fine detail. This is a visual aid, not proof of correct focus: scratches
    and specular reflections can also highlight. Input is uint8 HxWx3 BGR.
    """
    gray = cv2.cvtColor(preview, cv2.COLOR_BGR2GRAY)
    smooth = cv2.GaussianBlur(gray, (3, 3), .7)
    detail = np.abs(cv2.Laplacian(smooth, cv2.CV_32F, ksize=1))
    mask = (detail >= SENSITIVITIES.get(sensitivity, 18.)).astype(np.uint8)
    result = preview.copy()
    alpha = OPACITIES.get(opacity, .75)
    # OpenCV blending avoids large masked float arrays on busy PCB images.
    tint = np.empty_like(preview)
    tint[:] = COLOURS.get(colour, COLOURS['Red'])
    cv2.addWeighted(preview, 1. - alpha, tint, alpha, 0., dst=tint)
    cv2.copyTo(tint, mask, dst=result)
    return result
