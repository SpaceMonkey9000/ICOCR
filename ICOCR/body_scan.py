"""Optional body crop around the unchanged OCR engine, with explicit coordinates."""
from config_loader import tuning
from copy import deepcopy
import os
import time
import numpy as np
from body_locator import locate_body, body_crop, overlap_fraction
import re
from scan_result import build_scan_result
from ocr_core import candidate_id, warped_size

# Four-digit markings are normally suppressed as resistor codes (4701, 1001).
# On an IC body they can be the part marking itself (ST prints "2904" for an
# LM2904). Resistor text fills its body; IC text is small relative to the body.
BODY_NUMERIC_SCORE = tuning('selection.body_numeric_score')
BODY_NUMERIC_TEXT_RATIO = tuning('selection.body_numeric_text_ratio')
BODY_MIN_FRACTION = tuning('crop.minimum_body_fraction')   # geometric body vs selection area (0.8.3.5)


def mark_body_numeric(rows, body_box):
    body_short = min(warped_size(body_box))
    marked = []
    for row in rows:
        if (not row.get('ic_numeric') and re.fullmatch(r'[0-9]{4}', row['key']) and row.get('box') and
                row.get('score', 0) >= BODY_NUMERIC_SCORE and body_short > 0 and
                min(warped_size(row['box'])) <= BODY_NUMERIC_TEXT_RATIO*body_short and
                not row.get('conflicts')):
            row['rank'] = row.get('rank', 0) - .35  # below any part-like text (YYWW date codes look alike)
            row.update(ic_numeric=True, ic_numeric_evidence='detected IC body', kind='numeric',
                       status='Numeric marking on IC body — identity unknown',
                       evidence=row.get('evidence', '')+'; small text on detected body')
            marked.append(row)
    return marked


def body_min_fraction():
    try:
        value = float(os.environ.get('ICOCR_BODY_MIN_FRACTION', BODY_MIN_FRACTION))
        return value if np.isfinite(value) and 0 <= value <= 1 else BODY_MIN_FRACTION
    except ValueError:
        return BODY_MIN_FRACTION


def plausible_body(crop, detection):
    """0.8.3.5: a geometric 'body' covering under 6% of the selection is a
    pin-1 mark, glare or a text-free patch, not the IC (ICBENCH test_image_018:
    2.4%, no text inside; every useful body covered at least 8.7%). Scan the
    full selection directly instead of reading the crop and then recovering."""
    if detection.get('status') != 'detected' or detection.get('source') == 'model' or not detection.get('box'):
        return detection
    import cv2
    h, w = crop.shape[:2]
    fraction = abs(float(cv2.contourArea(np.asarray(detection['box'], np.float32)))) / max(1., h * w)
    minimum = body_min_fraction()
    if fraction >= minimum:
        return detection
    return dict(detection, status='fallback', box=None, attempted_box=detection['box'],
                body_fraction=round(fraction, 4),
                reason=f'Body outline too small for the selection ({fraction:.1%} < {minimum:.0%})')


def geometric_fallback(crop, reason):
    """Preserve the historical model-unavailable -> geometric fallback, visibly."""
    result = locate_body(crop)
    result.update(requested_source='model', model_fallback_reason=reason)
    return result


def _recovery_read(engine, crop, read_started, ocr_options):
    """Full-selection recovery read. A live scan gets only what is left of the
    live retry budget that the body-crop read started (0.8.8), not a fresh one."""
    if not ocr_options.get('live'):
        return engine.read(crop, **ocr_options)
    budget = getattr(engine, 'live_retry_budget', None)
    if not isinstance(budget, (int, float)) or isinstance(budget, bool):
        budget = tuning('ocr_core.live_retry_budget_seconds')
    remaining = max(0., float(budget) - (time.monotonic() - read_started))
    missing = object()
    previous = vars(engine).get('live_retry_budget', missing) if hasattr(engine, '__dict__') else missing
    engine.live_retry_budget = remaining
    try:
        return engine.read(crop, **ocr_options)
    finally:
        if previous is missing:
            try:
                del engine.live_retry_budget
            except AttributeError:
                pass
        else:
            engine.live_retry_budget = previous


def read_with_body(engine, crop, *, enabled=False, detection=None, **ocr_options):
    """detection: optional precomputed body (e.g. from the trained detector);
    otherwise the geometric locator runs when enabled."""
    started = time.monotonic()
    if detection is not None:
        detection = dict(detection)
    else:
        detection = (locate_body(crop) if enabled else
                     dict(status='disabled',reason='Body cropping disabled',box=None,score=0.,milliseconds=0.))
    detection = plausible_body(crop, detection)
    work,offset = body_crop(crop,detection) if detection['status']=='detected' else (crop,[0,0])
    # 0.8.3.4: a failed body-crop pass is followed by a full-selection recovery
    # with its own retry, so the crop pass defers its no-selection retry.
    engine.defer_retry = (detection['status'] == 'detected' and
                          os.environ.get('ICOCR_DEFER_BODY_RETRY', '1') != '0')
    read_started = time.monotonic()
    try:
        rows,_ = engine.read(work,**ocr_options)
    finally:
        engine.defer_retry = False
    rows,diagnostics = deepcopy((rows,engine.last_diagnostics))
    if detection['status']=='detected':
        seen = set()
        def restore(value):
            if isinstance(value,dict):
                if id(value) in seen:
                    return
                seen.add(id(value))
                if value.get('box') is not None:
                    value['box'] = (np.asarray(value['box'],dtype=float)+offset).tolist()
                for child in value.values():
                    restore(child)
            elif isinstance(value,list):
                for child in value:
                    restore(child)
        restore(rows);restore(diagnostics)
        all_rows = diagnostics.get('all_candidates',rows)
        inside = lambda r: bool(r.get('box')) and overlap_fraction(r['box'],detection['box'])>=.80
        diagnostics['outside_body_candidates'] = [r for r in all_rows if not inside(r)]
        all_rows = [r for r in all_rows if inside(r)]
        rows = [r for r in rows if inside(r)]
        for row in all_rows + rows:
            row['body_evidence'] = True
        eligible = {candidate_id(r) for r in rows}
        rows += [r for r in mark_body_numeric(all_rows, detection['box'])
                 if candidate_id(r) not in eligible]
        decision = build_scan_result(rows,all_rows,ocr_options.get('catalog'))
        for row in decision['all_candidates']:
            row['body_box'] = detection['box']
        if decision.get('provisional') is not None:
            decision['provisional']['body_box'] = detection['box']
        diagnostics['scan_result'] = decision
        diagnostics['all_candidates'] = all_rows
        diagnostics['candidates'] = rows
        rows = decision['display_candidates']
        detection['status'] = 'applied'
        detection['crop_offset'] = offset
        detection['crop_size'] = [work.shape[1],work.shape[0]]
    # One bounded recovery scan, using original pixels and selection coordinates.
    # Do not recurse: recovery must never reapply the same failing body mask.
    if (getattr(engine, 'acquisition_only', False) is not True and detection['status'] == 'applied' and
            not diagnostics.get('scan_result', {}).get('selected')):
        cropped_diagnostics = diagnostics
        full_rows, _ = _recovery_read(engine, crop, read_started, ocr_options)
        # 0.8.4.3: no deep copy. Nothing below changes these rows or any nested
        # value (only top-level keys of this dict copy), and the engine replaces,
        # never edits, last_diagnostics on its next read.
        full_diagnostics = dict(engine.last_diagnostics)
        recovered = bool(full_diagnostics.get('scan_result', {}).get('selected'))
        if recovered:
            rows, diagnostics = full_rows, full_diagnostics
            detection = dict(detection, status='fallback', box=None,
                             attempted_box=detection['box'],
                             reason='Body scan failed; recovered from full selection')
        diagnostics['body_recovery'] = dict(attempted=True, recovered=recovered,
            cropped_scan_result=cropped_diagnostics.get('scan_result'),
            full_scan_result=full_diagnostics.get('scan_result'))
        timings = {}
        for source in (cropped_diagnostics, full_diagnostics):
            for key, value in source.get('timings', {}).items():
                if isinstance(value, list):
                    timings.setdefault(key, []).extend(value)
                elif isinstance(value, (int, float)):
                    timings[key] = timings.get(key, 0.) + value
        diagnostics['timings'] = timings
        for key in ('ocr_calls', 'retry_calls'):
            diagnostics[key] = (cropped_diagnostics.get(key, 0) +
                                full_diagnostics.get(key, 0))
    if getattr(engine, 'acquisition_only', False) is True:
        diagnostics['acquisition_only'] = True
        diagnostics['body_recovery'] = dict(attempted=False, recovered=False,
                                             reason='Observation prototype: wait for new evidence')
    diagnostics['body_detection'] = detection
    diagnostics['scan_input'] = dict(
        requested=('model body' if detection.get('requested_source', detection.get('source')) == 'model' else 'geometric body') if enabled else 'full selection',
        actual=('model body' if detection.get('source') == 'model' else 'geometric body') if detection['status'] == 'applied' else 'full selection',
        fallback=bool(detection.get('model_fallback_reason')) or detection['status'] not in ('applied','disabled'),
        reason='; '.join(x for x in (detection.get('model_fallback_reason'), detection.get('reason')) if x),
        full_selection_retry=diagnostics.get('body_recovery', {}))
    timings = diagnostics.setdefault('timings',{})
    timings['body_detection_ms'] = detection['milliseconds']
    elapsed = time.monotonic()-started
    timings['total_ms'] = elapsed*1000
    engine.last_diagnostics = diagnostics
    return rows,elapsed
