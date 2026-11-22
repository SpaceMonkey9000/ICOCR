"""OCR region geometry. Body boundaries remain unmodified; only scan ROI is padded."""

def expand_body_roi(roi, source_size, fraction=0.15, minimum_pixels=16):
    """Expand a normalized body ROI in image pixels and clip to the full frame.

    An extra 15% per side (at least 16 source pixels) allows minor motion
    between detection and scanning without excluding package edges.
    """
    width, height = source_size
    if width <= 0 or height <= 0:
        raise ValueError('Invalid source dimensions')
    x0, y0, x1, y1 = (float(v) for v in roi)
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        raise ValueError('Invalid normalized body ROI')
    dx = max((x1-x0)*width*fraction, minimum_pixels)/width
    dy = max((y1-y0)*height*fraction, minimum_pixels)/height
    return (max(0., x0-dx), max(0., y0-dy), min(1., x1+dx), min(1., y1+dy))
