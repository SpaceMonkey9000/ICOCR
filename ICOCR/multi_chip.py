"""Experimental multi-chip scan (0.8.3.7).

One selection can contain several ICs. This module finds them and reads each
one with the normal single-chip pipeline, unchanged:

1. Discovery: a fast text pass (0/90-degree detection, each line read both
   ways) over the selection, in overlapping tiles when the selection is large,
   so small markings keep enough pixels.
2. Grouping: printed lines of similar height and direction that sit close
   together form one marking block. A block needs at least one part-like line
   (letters and digits, 4+ characters, not a reference designator such as R45
   or IC3); resistor codes and silkscreen alone never start a chip.
3. Trained detector bodies (when the chip detector model is loaded) are added
   as chips of their own, and absorb text blocks lying on them.
4. Each chip is scanned with ``body_scan.read_with_body`` on a region around
   it. Text of the other chips in that region is painted over first, so a
   neighbour's marking cannot become this chip's reading.

Nothing here changes the single-chip scan. Readings are evidence, not identity,
exactly as in the single-chip pipeline.
"""
import logging
import time
from copy import deepcopy

import cv2
import numpy as np

from ocr_core import normalize, REFERENCE, warped_size, ScanCancelled

VERSION = 'multi-1'

TILE_SIDE = 1800          # discovery tile size in source pixels (scaled to <= 1400 by OCR)
TILE_OVERLAP = .18        # fraction of a tile shared with its neighbour
MAX_CHIPS = 10            # per scan; the largest/strongest blocks are read first
SEED_SCORE = .60          # OCR score needed for a line to start a chip
LINK_GAP = 1.25           # lines join a block within this many line heights
HEIGHT_RATIO = 2.4        # ... and when their character heights are this similar
ANGLE_LIMIT = 22.         # ... and their directions differ by less than this (degrees)
MIN_TEXT_HEIGHT = 6.      # source pixels; smaller detections are noise for discovery
MIN_PROBE_HEIGHT = 14.    # part-like text below this (OCR probe pixels) triggers tiles


# --------------------------------------------------------------------- lines

def _line(raw):
    box = np.asarray(raw['box'], dtype=np.float32)
    width, height = warped_size(box)
    direction = box[1] - box[0]
    angle = float(np.degrees(np.arctan2(direction[1], direction[0]))) % 180.
    return dict(text=raw.get('text', ''), key=normalize(raw.get('text', '')),
                score=float(raw.get('score', 0.)), box=box, centre=box.mean(axis=0),
                width=float(width), height=float(height), angle=angle)


def seed_line(line):
    """Part-like printed text can start a chip; board text cannot."""
    key = line['key']
    if line['score'] < SEED_SCORE or len(key) < 4 or REFERENCE.fullmatch(key):
        return False
    letters = sum(c.isalpha() for c in key)
    digits = sum(c.isdigit() for c in key)
    return letters >= 1 and digits >= 1


def _tiles(shape):
    h, w = shape[:2]
    def spans(length):
        if length <= TILE_SIDE * 1.15:
            return [(0, length)]
        count = int(np.ceil((length - TILE_SIDE * TILE_OVERLAP) / (TILE_SIDE * (1 - TILE_OVERLAP))))
        count = max(2, count)
        size = int(np.ceil(length / (count - (count - 1) * TILE_OVERLAP)))
        step = (length - size) / (count - 1)
        return [(int(round(i * step)), min(length, int(round(i * step)) + size)) for i in range(count)]
    return [(x0, y0, x1, y1) for y0, y1 in spans(h) for x0, x1 in spans(w)]


def _iou(a, b):
    pa, pb = cv2.convexHull(a), cv2.convexHull(b)
    inter, _ = cv2.intersectConvexConvex(pa, pb)
    union = abs(cv2.contourArea(pa)) + abs(cv2.contourArea(pb)) - inter
    return float(inter / union) if union > 0 else 0.


def _discovery_pass(engine, image, window, lines, cancelled):
    """One fast OCR pass over ``window`` of ``image``; adds to ``lines``."""
    x0, y0, x1, y1 = window
    if cancelled is not None and cancelled():
        raise ScanCancelled()
    tile = image[y0:y1, x0:x1]
    if min(tile.shape[:2]) < 12:
        return 0
    engine._read_fast(tile, orientations=(0, 1), treatment='Local contrast')
    best = {}
    for raw in engine.last_diagnostics.get('raw', []):
        ident = (raw.get('pass_id'), raw.get('crop_id'))
        if ident not in best or raw['score'] > best[ident]['score']:
            best[ident] = raw
    for raw in best.values():
        line = _line(dict(raw, box=(np.asarray(raw['box'], float) + [x0, y0]).tolist()))
        if line['height'] < MIN_TEXT_HEIGHT or line['width'] < MIN_TEXT_HEIGHT:
            continue
        # Tiles and the two detection turns overlap: keep the fuller reading.
        twin = next((i for i, old in enumerate(lines) if _iou(old['box'], line['box']) > .45), None)
        if twin is None:
            lines.append(line)
        elif (len(line['key']), line['score']) > (len(lines[twin]['key']), lines[twin]['score']):
            lines[twin] = line
    return engine.last_diagnostics.get('ocr_calls', 0)


def discover_lines(engine, image, cancelled=None):
    """Printed lines in ``image`` coordinates, one entry per physical line.

    One pass over the whole selection first (the OCR scales its long side to
    1400 px). Only when that leaves part-like text small (< MIN_PROBE_HEIGHT
    probe pixels) or finds none, overlapping tiles are read at higher
    resolution as well. Measured on a 4K board: one pass 1.3 s, two tiles 4 s.
    """
    lines, passes = [], 0
    saved = (getattr(engine, '_timings', None), getattr(engine, '_extra_pass', False))
    engine._timings, engine._extra_pass = None, False
    h, w = image.shape[:2]
    try:
        passes += _discovery_pass(engine, image, (0, 0, w, h), lines, cancelled)
        tiles = _tiles(image.shape)
        scale = min(2., 1400 / max(h, w))
        seeds = [l for l in lines if seed_line(l)]
        small = not seeds or min(l['height'] for l in seeds) * scale < MIN_PROBE_HEIGHT
        if len(tiles) > 1 and small:
            for window in tiles:
                passes += _discovery_pass(engine, image, window, lines, cancelled)
    finally:
        engine._timings, engine._extra_pass = saved
    return lines, passes


# ------------------------------------------------------------------ grouping

def _expanded(line, gap):
    """Line quad grown by ``gap`` line heights on every side."""
    box = line['box']
    centre = line['centre']
    u = box[1] - box[0]
    u = u / max(1e-6, np.linalg.norm(u))
    v = np.array([-u[1], u[0]], dtype=np.float32)
    grow = gap * line['height']
    out = []
    for point in box:
        d = point - centre
        out.append(point + np.sign(d @ u) * u * grow + np.sign(d @ v) * v * grow)
    return np.asarray(out, np.float32)


def _linked(a, b):
    small, large = sorted((a['height'], b['height']))
    if small <= 0 or large / small > HEIGHT_RATIO:
        return False
    difference = abs(a['angle'] - b['angle']) % 180.
    if min(difference, 180. - difference) > ANGLE_LIMIT:
        # Short lines (2-3 characters) have unreliable directions; allow them.
        if min(a['width'] / max(1., a['height']), b['width'] / max(1., b['height'])) > 2.2:
            return False
    gap = LINK_GAP * .5
    inter, _ = cv2.intersectConvexConvex(cv2.convexHull(_expanded(a, gap)),
                                         cv2.convexHull(_expanded(b, gap)))
    return inter > 0


def group_lines(lines):
    """Marking blocks: connected lines containing at least one part-like line."""
    parent = list(range(len(lines)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(len(lines)):
        for j in range(i + 1, len(lines)):
            if find(i) != find(j) and _linked(lines[i], lines[j]):
                parent[find(i)] = find(j)
    blocks = {}
    for i in range(len(lines)):
        blocks.setdefault(find(i), []).append(lines[i])
    result = []
    for members in blocks.values():
        seeds = [m for m in members if seed_line(m)]
        if not seeds:
            continue
        points = np.vstack([m['box'] for m in members])
        result.append(dict(lines=members, seeds=seeds, points=points,
                           height=float(np.median([m['height'] for m in members])),
                           strength=max(m['score'] * len(m['key']) for m in seeds),
                           source='text'))
    return result


# ------------------------------------------------------------------- regions

def _bounds(points):
    points = np.asarray(points, float).reshape(-1, 2)
    return points.min(axis=0), points.max(axis=0)


def _region(block, shape):
    """Upright scan region around a block: text plus room for the chip body."""
    h, w = shape[:2]
    if block.get('body') is not None:
        lo, hi = _bounds(block['body'])
        margin = .10 * (hi - lo) + 4
    else:
        lo, hi = _bounds(block['points'])
        size = hi - lo
        margin = np.maximum(2.2 * block['height'], .45 * size.max())
    lo = np.maximum(np.floor(lo - margin), 0).astype(int)
    hi = np.minimum(np.ceil(hi + margin), [w, h]).astype(int)
    return [int(lo[0]), int(lo[1]), int(hi[0]), int(hi[1])]


def _inside(point, polygon):
    return cv2.pointPolygonTest(np.asarray(polygon, np.float32).reshape(-1, 1, 2),
                                (float(point[0]), float(point[1])), False) >= 0


def merge_detector_bodies(blocks, detections, shape, offset=(0, 0)):
    """Detector bodies become chips; text blocks lying on a body join it.

    ``detections`` are whole-frame detector results; ``offset`` is the selection's
    top-left corner in frame pixels. Bodies must lie fully inside the selection.
    """
    h, w = shape[:2]
    ox, oy = offset
    chips = []
    for found in detections or []:
        if found.get('truncated'):
            continue
        corners = np.asarray(found.get('polygon') or [[found['box'][0], found['box'][1]],
                             [found['box'][2], found['box'][1]], [found['box'][2], found['box'][3]],
                             [found['box'][0], found['box'][3]]], float) - [ox, oy]
        if corners[:, 0].min() < 0 or corners[:, 1].min() < 0 or \
                corners[:, 0].max() > w or corners[:, 1].max() > h:
            continue
        mask = found.get('mask_polygon')
        chips.append(dict(lines=[], seeds=[], points=corners, body=corners.tolist(),
                          mask_polygon=((np.asarray(mask, float) - [ox, oy]).tolist() if mask else None),
                          angle=found.get('angle', 0.), score=float(found.get('score', 0.)),
                          height=0., strength=10. + float(found.get('score', 0.)), source='detector'))
    remaining = []
    for block in blocks:
        centre = np.asarray(block['points']).mean(axis=0)
        host = next((c for c in chips if _inside(centre, c['body'])), None)
        if host is None:
            remaining.append(block)
        else:
            host['lines'] += block['lines']
            host['seeds'] += block['seeds']
    return chips + remaining


def _merge_overlapping(blocks, shape):
    """Two text blocks whose cores overlap are one chip (e.g. split logo/line)."""
    merged = True
    while merged:
        merged = False
        for i in range(len(blocks)):
            for j in range(i + 1, len(blocks)):
                a, b = blocks[i], blocks[j]
                if 'body' in a or 'body' in b:
                    continue
                la, ha = _bounds(a['points'])
                lb, hb = _bounds(b['points'])
                pad = .5 * max(a['height'], b['height'])
                if np.all(la - pad <= hb) and np.all(lb - pad <= ha):
                    blocks[i] = dict(a, lines=a['lines'] + b['lines'], seeds=a['seeds'] + b['seeds'],
                                     points=np.vstack([a['points'], b['points']]),
                                     height=float(np.median([m['height'] for m in a['lines'] + b['lines']])),
                                     strength=max(a['strength'], b['strength']))
                    del blocks[j]
                    merged = True
                    break
            if merged:
                break
    return blocks


def _mask_others(region_image, region, chip, lines):
    """Paint over text of other chips inside this chip's region."""
    x0, y0 = region[:2]
    own = {id(line) for line in chip['lines']}
    out = None
    for line in lines:
        if id(line) in own:
            continue
        box = _expanded(line, .35) - [x0, y0]
        if box[:, 0].max() < 0 or box[:, 1].max() < 0 or \
                box[:, 0].min() > region_image.shape[1] or box[:, 1].min() > region_image.shape[0]:
            continue
        if chip.get('body') is not None and _inside(line['centre'], chip['body']):
            continue
        if not any(_inside(line['centre'] , other) for other in chip.get('other_cores', [])):
            continue
        if out is None:
            out = region_image.copy()
        polygon = np.round(box).astype(np.int32)
        ring = cv2.dilate(_fill(out.shape, polygon), np.ones((9, 9), np.uint8))
        inner = _fill(out.shape, polygon)
        border = (ring != 0) & (inner == 0)
        colour = np.median(out[border], axis=0) if np.any(border) else np.median(out.reshape(-1, 3), axis=0)
        out[inner != 0] = colour.astype(np.uint8)
    return region_image if out is None else out


def _fill(shape, polygon):
    mask = np.zeros(shape[:2], np.uint8)
    cv2.fillConvexPoly(mask, polygon, 255)
    return mask


# ---------------------------------------------------------------------- scan

def _shift(value, offset, seen=None):
    """Move every 'box'/'body_box' in nested results by offset (in place)."""
    seen = set() if seen is None else seen
    if isinstance(value, dict):
        if id(value) in seen:
            return
        seen.add(id(value))
        for name in ('box', 'body_box', 'attempted_box', 'mask_polygon'):
            if value.get(name) is not None:
                try:
                    value[name] = (np.asarray(value[name], float) + offset).tolist()
                except (TypeError, ValueError):
                    pass
        for child in value.values():
            _shift(child, offset, seen)
    elif isinstance(value, list):
        for child in value:
            _shift(child, offset, seen)


def plan(engine, image, *, detections=None, offset=(0, 0), cancelled=None, max_chips=MAX_CHIPS):
    """Chips to read in ``image`` (the selection), strongest first."""
    started = time.perf_counter()
    lines, passes = discover_lines(engine, image, cancelled)
    blocks = _merge_overlapping(group_lines(lines), image.shape)
    chips = merge_detector_bodies(blocks, detections, image.shape, offset)
    chips.sort(key=lambda c: c['strength'], reverse=True)
    skipped = max(0, len(chips) - max_chips)
    chips = chips[:max_chips]
    cores = []
    for chip in chips:
        chip['region'] = _region(chip, image.shape)
        if chip.get('body') is not None:
            cores.append(chip['body'])
        else:
            lo, hi = _bounds(chip['points'])
            pad = .6 * chip['height']
            cores.append([[lo[0]-pad, lo[1]-pad], [hi[0]+pad, lo[1]-pad],
                          [hi[0]+pad, hi[1]+pad], [lo[0]-pad, hi[1]+pad]])
    for chip, core in zip(chips, cores):
        chip['core'] = core
        chip['other_cores'] = [c for c in cores if c is not core]
    return dict(chips=chips, lines=lines, discovery_passes=passes, skipped=skipped,
                milliseconds=(time.perf_counter() - started) * 1000)


def read_chips(engine, image, *, read, auto_body=True, detections=None, offset=(0, 0),
               cancelled=None, max_chips=MAX_CHIPS, **ocr_options):
    """Read every chip in ``image``.

    ``read`` is ``body_scan.read_with_body`` (injected for tests). Results use
    ``image`` (selection) coordinates. Returns (chips, summary).
    """
    started = time.monotonic()
    layout = plan(engine, image, detections=detections, offset=offset,
                  cancelled=cancelled, max_chips=max_chips)
    results = []
    for index, chip in enumerate(layout['chips']):
        if cancelled is not None and cancelled():
            raise ScanCancelled()
        x0, y0, x1, y1 = chip['region']
        region_image = image[y0:y1, x0:x1]
        if min(region_image.shape[:2]) < 16:
            continue
        work = _mask_others(region_image, chip['region'], chip, layout['lines'])
        detection = None
        if chip.get('body') is not None:
            body = (np.asarray(chip['body'], float) - [x0, y0]).tolist()
            detection = dict(status='detected', reason='Detector IC body (multi-chip)', box=body,
                             score=chip['score'], source='model', angle=chip.get('angle', 0.),
                             milliseconds=0.)
            if chip.get('mask_polygon'):
                detection.update(mask_polygon=(np.asarray(chip['mask_polygon'], float) - [x0, y0]).tolist(),
                                 task='segment')
        error = None
        try:
            rows, elapsed = read(engine, work, enabled=auto_body or detection is not None,
                                 detection=detection, **ocr_options)
            # 0.8.4.3: one copy of both (shared rows stay shared, so the joint
            # shift below moves each nested box exactly once, as before).
            rows, diagnostics = deepcopy((rows, engine.last_diagnostics))
        except ScanCancelled:
            raise
        except Exception as exc:   # one bad chip must not lose the others
            logging.exception('Multi-chip scan failed for chip %d', index)
            rows, elapsed, diagnostics, error = [], 0., {}, str(exc)
        shifted = set()
        _shift(rows, [x0, y0], shifted)
        _shift(diagnostics, [x0, y0], shifted)
        decision = diagnostics.get('scan_result') or {}
        target, status = decision.get('selected'), 'selected'
        if target is None and decision.get('provisional') is not None:
            target, status = decision['provisional'], 'provisional'
        if target is None:
            target = unconfirmed(decision)
            status = 'unconfirmed' if target is not None else ('error' if error else 'none')
        body = (diagnostics.get('body_detection') or {})
        results.append(dict(
            index=index, source=chip['source'], region=[x0, y0, x1, y1], core=chip['core'],
            discovery=[dict(text=l['text'], score=l['score']) for l in chip['lines']],
            rows=rows, scan_result=decision, selected=decision.get('selected'),
            provisional=decision.get('provisional'), target=target, status=status,
            body_box=body.get('box') if body.get('status') == 'applied' else chip.get('body'),
            body_status=body.get('status'), elapsed=elapsed, error=error,
            diagnostics=diagnostics))
    results = deduplicate(results)
    summary = dict(version=VERSION, chips=len(results), planned=len(layout['chips']),
                   skipped=layout['skipped'], discovery_lines=len(layout['lines']),
                   discovery_passes=layout['discovery_passes'],
                   discovery_ms=layout['milliseconds'],
                   total_ms=(time.monotonic() - started) * 1000)
    return results, summary


def unconfirmed(decision):
    """Best part-like reading the selection rules did not pick (e.g. a chip cut
    by the frame edge). Shown as 'Unconfirmed', never as a pick."""
    for row in decision.get('all_candidates') or []:
        key = row.get('key', '')
        if (row.get('box') is not None and len(key) >= 4 and not REFERENCE.fullmatch(key) and
                any(c.isalpha() for c in key) and any(c.isdigit() for c in key) and
                not row.get('orientation_alternative') and row.get('score', 0) >= SEED_SCORE):
            return dict(row, multi_unconfirmed=True)
    return None


def to_frame(chips, offset):
    """Selection coordinates -> frame coordinates (in place)."""
    ox, oy = offset
    for chip in chips:
        _shift(chip, [ox, oy])
        x0, y0, x1, y1 = chip['region']
        chip['region'] = [x0 + ox, y0 + oy, x1 + ox, y1 + oy]
        chip['core'] = (np.asarray(chip['core'], float) + [ox, oy]).tolist()
    return chips


def deduplicate(results):
    """Overlapping regions can read the same printed line twice: keep one."""
    kept = []
    for chip in sorted(results, key=lambda c: (c['selected'] is None, c['target'] is None)):
        target = chip['target']
        if target is not None and target.get('box') is not None:
            centre = np.asarray(target['box'], float).mean(axis=0)
            twin = next((k for k in kept if k['target'] is not None and k['target'].get('box') is not None
                         and k['target']['key'] == target['key']
                         and np.linalg.norm(np.asarray(k['target']['box'], float).mean(axis=0) - centre)
                         < max(warped_size(target['box'])[1], 8) * 2), None)
            if twin is not None:
                continue
        kept.append(chip)
    kept.sort(key=lambda c: c['index'])
    for number, chip in enumerate(kept, 1):
        chip['number'] = number
    return kept


EXACT_COLOUR = '#65f2c0'      # same colours as the single-chip overlay
OTHER_COLOUR = '#ffd37a'
WEAK_COLOUR = '#b8c4cf'


def reading_of(chip):
    """The row shown for a chip: technician choice, else the automatic target."""
    return chip.get('choice') or chip.get('target')


def label_for(chip):
    """Marking text shown for one chip."""
    row = reading_of(chip)
    if chip.get('error') and row is None:
        return 'OCR error'
    if row is None:
        return 'No reading'
    if row.get('ocr_correction') and row.get('resolved_partnumber'):
        return row['resolved_partnumber']
    return row.get('text') or row.get('key', '')


def describe(chip, database_loaded):
    """(label, colour) for the overlay; mirrors the single-chip wording."""
    row = reading_of(chip)
    title = f"{chip.get('number', '?')}  " + label_for(chip)
    if row is None:
        return title + ('\n' + chip['error'] if chip.get('error') else ''), WEAK_COLOUR
    matches = row.get('trusted_database_matches', [])
    exact = bool(matches) and all(m.get('match_type') == 'exact' for m in matches)
    colour = EXACT_COLOUR if exact and not row.get('database_ambiguous') else OTHER_COLOUR
    description = row.get('function_summary') or ('No database match' if database_loaded
                                                   else 'Load database for description')
    if row.get('technician_choice'):
        title += '  ✓'
    elif row.get('multi_unconfirmed'):
        title, colour = title + '  (unconfirmed)', WEAK_COLOUR
    elif not matches:
        title += '  (provisional)'   # as the single-chip 'Provisional:' prefix
    if row.get('ocr_correction'):
        description = 'Corrected from ' + row.get('text', '') + ': ' + description
    elif matches and not exact:
        description = 'Partial match: ' + description
    if len(description) > 90:
        description = description[:87] + '…'
    return title + '\n' + description, colour


def list_label(chip):
    row = reading_of(chip)
    mark = ('✓ ' if row is not None and row.get('technician_choice') else
            '★ ' if chip.get('selected') is not None and row is chip.get('selected') else '  ')
    text = label_for(chip)
    if row is not None and row.get('multi_unconfirmed'):
        text += ' (unconfirmed)'
    summary = (row or {}).get('function_summary')
    return f"Chip {chip.get('number', '?')}: {mark}{text}" + (f' — {summary}' if summary else '')
