"""Local OCR; no image uploads. Model weights are bundled by the pinned package."""
from config_loader import tuning, rule_enabled
import os
import re
import time
import cv2
import numpy as np
from marking_rules import part_pattern, joined_line_marking, origin_exclusion


def normalize(text):
    return re.sub(r'[^A-Z0-9-]', '', text.upper())


def crop_roi(frame, roi):
    """Copy of the fractional ROI (x1, y1, x2, y2), never empty.

    0.8.4.3: a missing frame raises a clear ValueError instead of an
    AttributeError, and a degenerate or out-of-frame ROI is clamped to at
    least one pixel so callers that resize the crop never see an empty array.
    """
    if frame is None:
        raise ValueError('No image to crop: the frame is missing (camera or file read failed).')
    h, w = frame.shape[:2]
    if h < 1 or w < 1:
        raise ValueError('No image to crop: the frame is empty.')
    x1, y1, x2, y2 = roi
    left = min(max(0, int(x1*w)), w-1)
    top = min(max(0, int(y1*h)), h-1)
    right = max(left+1, min(w, int(x2*w)))
    bottom = max(top+1, min(h, int(y2*h)))
    return frame[top:bottom, left:right].copy()


def _setting(key, default=0):
    """Tuning value, or ``default`` for a configuration without the key."""
    try:
        return tuning(key)
    except KeyError:
        return default


def scaled(image, scale):
    """Resize by ``scale``: INTER_AREA when shrinking (no aliasing of fine
    print), INTER_CUBIC when enlarging (unchanged)."""
    return cv2.resize(image, None, fx=scale, fy=scale,
                      interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)


def split_candidates(observations, known=(), modes=1, copy=True):
    """(eligible rows, rotation, all rows) from one select_candidates pass.

    select_candidates(show_all=False) is the retention_eligible subsequence of
    the show_all=True result: conflicts are computed against all groups in
    both cases and the rank sort is stable. A deep copy keeps the two lists as
    independent as two separate calls made them.
    """
    import copy as copying
    every, _ = select_candidates(observations, known, modes=modes, show_all=True)
    rows = [r for r in every if r['retention_eligible']]
    if copy:
        rows = copying.deepcopy(rows)
    return rows, (rows[0]['rotation'] if rows else 0), every


from ic_preprocessing import preprocess, configuration, recognition_preprocessing
from ic_preprocessing import VERSION as PREPROCESSING_VERSION


def enhance(crop, mode='Original'):
    return preprocess(crop, mode)

# Format hints, not a component catalogue. They never establish identity.
from config_loader import get_config, configuration_diagnostics
from database_rules import extra_prefixes
_PREFIXES = get_config('rules/part_prefixes.json')['prefixes'] + extra_prefixes()
_BROAD = [row['pattern'] for row in get_config('rules/device_families.json')['broad_patterns'] if row['enabled']]
if _PREFIXES:
    _BROAD.insert(0, r'(?:' + '|'.join(re.escape(prefix) for prefix in _PREFIXES) + r')\d[A-Z0-9/.-]*')
FAMILY = re.compile(r'^(?:' + '|'.join('(?:' + pattern + ')' for pattern in _BROAD) + r')$' if _BROAD else r'(?!)')

REFERENCE = re.compile(r'^(?:R|C|L|D|Q|U|IC|TP|LED|JP|J|CN|RN|RA|CA)\d{1,5}$')


def numeric_marking(key):
    # Short numeric resistor values stay excluded. Numeric text is a marking,
    # never proof of an IC identity (it may also be a lot/date code).
    return bool(re.fullmatch(r'[0-9]{5,12}', key))


def kind(key, known=()):
    if key in known:
        return 'saved'
    if numeric_marking(key):
        return 'numeric'
    if (rule_enabled('exclude.pcb_reference') and REFERENCE.fullmatch(key)) or not (any(c.isalpha() for c in key) and any(c.isdigit() for c in key)):
        return 'context'
    if (FAMILY.fullmatch(key) or part_pattern(key)) and len(key) >= 5:
        return 'family'
    if 6 <= len(key) <= 24 and re.fullmatch(r'[A-Z]{2,6}\d[A-Z0-9/-]*',key):
        return 'unknown'
    return 'context'


def same_text_region(a, b):
    """Alternative readings must occupy the same physical printed region."""
    if not a or not b:
        return True  # Missing geometry remains conservatively ambiguous.
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    area_a, area_b = abs(cv2.contourArea(a)), abs(cv2.contourArea(b))
    if min(area_a, area_b) <= 0:
        return False
    overlap, _ = cv2.intersectConvexConvex(cv2.convexHull(a), cv2.convexHull(b))
    return overlap / min(area_a, area_b) >= tuning('ocr_core.text_region_overlap')


def deduplicate_raw_lines(rows):
    """Merge identical overlapping readings, never separate physical lines.

    Keep treatment/reading-direction groups independent for benchmark consumers.
    Without geometry retain the row: text equality alone is insufficient.
    """
    result = []
    for original in rows:
        row = dict(original)
        match = next((i for i, old in enumerate(result)
                      if old.get('text', '').strip().upper() == row.get('text', '').strip().upper()
                      and old.get('rotation') == row.get('rotation')
                      and old.get('mode') == row.get('mode')
                      and old.get('box') and row.get('box')
                      and same_text_region(old['box'], row['box'])), None)
        if match is None:
            result.append(row)
        elif row.get('score', 0) > result[match].get('score', 0):
            result[match] = row
    return result


def candidate_id(row):
    return (row['key'], tuple(round(float(v), 3) for pt in row.get('box') or [] for v in pt))


def _box_bounds(box):
    """Axis-aligned float32 bounds of a box, or None without geometry
    (then same_text_region treats the pair as ambiguous)."""
    if box is None or len(box) == 0:
        return None
    points = np.asarray(box, dtype=np.float32).reshape(-1, 2)
    return (float(points[:, 0].min()), float(points[:, 1].min()),
            float(points[:, 0].max()), float(points[:, 1].max()))


def _bounds_disjoint(a, b):
    """True only when both bounds exist and are strictly separated, so the
    convex overlap in same_text_region is zero."""
    return (a is not None and b is not None and
            (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1]))


def select_candidates(observations, known=(), modes=3, show_all=False):
    """Pool orientations, with at most one vote per treatment. Prefixes rank only.

    0.8.8: cheap key/score/similarity tests run before the convex overlap test,
    and boxes whose bounds are strictly apart skip it (zero overlap can never
    reach a positive ocr_core.text_region_overlap). Results are unchanged.
    """
    from difflib import SequenceMatcher
    # The bounds pre-filter is exact only for a positive overlap threshold.
    prefilter = tuning('ocr_core.text_region_overlap') > 0
    bounds = _box_bounds if prefilter else (lambda box: None)
    groups = []
    for row in observations:
        key = row['key']
        row_bounds = None
        entry = None
        for g in groups:
            if g['key'] != key:
                continue
            if row_bounds is None:
                row_bounds = bounds(row.get('box'))
            if not _bounds_disjoint(row_bounds, g['bounds']) and same_text_region(row.get('box'), g['box']):
                entry = g
                break
        if entry is None:
            entry = dict(key=key, box=row.get('box'), readings={}, observations=[],
                         bounds=row_bounds if row_bounds is not None else bounds(row.get('box')))
            groups.append(entry)
        group = entry['readings']
        entry['observations'].append(dict(row))
        old = group.get(row['mode'])
        if old is None or row['score'] > old['score']:
            group[row['mode']] = row
    candidates = []
    for group in groups:
        key, readings = group['key'], group['readings']
        values=list(readings.values())
        score=sum(r['score'] for r in values)/len(values)
        support=len(values)
        mixed=any(c.isalpha() for c in key) and any(c.isdigit() for c in key)
        category=kind(key,known)
        eligible=(mixed or key in known or (numeric_marking(key) and score >= tuning('ocr_core.numeric_min_score'))) and not (rule_enabled('exclude.pcb_reference') and REFERENCE.fullmatch(key)) and (
            (support>=2 and score>=tuning('selection.repeated_min_score')) or (support==1 and score>=(tuning('selection.single_fast_score') if modes==1 else tuning('selection.single_full_score'))))
        if not eligible and not show_all:
            continue
        representative=max(values,key=lambda r:r['score'])
        rank=score+tuning('ranking.support_weight')*support+{'saved':tuning('ranking.saved_weight'),'family':tuning('ranking.family_weight'),'unknown':tuning('ranking.unknown_weight'),'numeric':tuning('ranking.numeric_weight'),'context':tuning('ranking.context_weight')}[category]
        candidates.append(dict(key=key,text=representative.get('text', key) if representative.get('origin_metadata') else key,score=score,rotation=representative['rotation'],
            support=support,modes=sorted(readings),kind=category,rank=rank,conflicts=[],
            box=representative.get('box'),
            observation_evidence=group['observations'],
            independent_frames=1, evidence_scope='one image; transforms are correlated',
            conflict_evidence=[], dismissed_conflicts=[],
            raw_text=representative.get('raw_text', representative.get('text', key)),
            whitespace_joined=any(r.get('whitespace_joined', False) for r in values),
            retention_eligible=eligible,
            orientation_alternative=all(r.get('orientation_alternative', False) for r in group['observations']),
            status='Numeric marking — identity unknown' if category=='numeric' else
                   'Saved marking match' if category=='saved' else
                   'Repeated marking — unverified' if support>=2 else 'Single-treatment reading — tentative',
            evidence=f'{support} treatment(s), one image; OCR score {score:.2f}; identity unverified'))
    fold=str.maketrans({'O':'0','I':'1','L':'1','B':'8','S':'5','Z':'2'})
    conflict_min_score = tuning('ocr_core.conflict_min_score')
    conflict_similarity = tuning('ocr_core.conflict_similarity')
    for group in groups:
        group['best_score'] = max(r['score'] for r in group['readings'].values())
        group['folded'] = group['key'].translate(fold)
    for row in candidates:
        key = row['key']
        folded = key.translate(fold)
        row_bounds = bounds(row.get('box'))
        for group in groups:
            other, readings = group['key'], group['readings']
            # Every test below is a pure filter; cheapest first (0.8.8).
            if other==key or group['best_score']<conflict_min_score:
                continue
            # A reading truncated at an edge (e.g. 4HC163D inside 74HC163D) is
            # missing evidence, not contradicting it. The shorter reading still
            # conflicts with the longer one, so only the complete reading survives.
            if len(other) < len(key) <= len(other)+2 and other in key:
                continue
            if _bounds_disjoint(row_bounds, group['bounds']):
                continue
            if not (group['folded']==folded or
                    SequenceMatcher(None,other,key).ratio()>=conflict_similarity):
                continue
            if not same_text_region(row.get('box'), group['box']):
                continue
            from selection_evidence import weak_conflict
            reason = weak_conflict(row['key'], other, row['observation_evidence'],
                                   group['observations'])
            detail = dict(key=other, score=max(r['score'] for r in group['observations']),
                          modes=sorted(readings), blocking=not bool(reason),
                          reason=reason or 'Comparable or insufficiently separated reading',
                          observations=group['observations'])
            row['conflict_evidence'].append(detail)
            if reason:
                row['dismissed_conflicts'].append(other)
            else:
                row['conflicts'].append(other)
        if row['conflicts']:
            row['status']='Conflicting readings'
    candidates.sort(key=lambda r:r['rank'],reverse=True)
    return candidates, candidates[0]['rotation'] if candidates else 0


def straighten(image, angle, return_matrix=False):
    """Expanded rotation canvas preserves all original pixels at the boundaries."""
    h,w = image.shape[:2]
    m = cv2.getRotationMatrix2D((w/2,h/2),angle,1)
    co,si = abs(m[0,0]),abs(m[0,1])
    nw,nh = int(h*si+w*co)+2,int(h*co+w*si)+2
    m[0,2] += nw/2-w/2
    m[1,2] += nh/2-h/2
    result = cv2.warpAffine(image,m,(nw,nh),flags=cv2.INTER_CUBIC,borderMode=cv2.BORDER_REPLICATE)
    return (result, m) if return_matrix else result


def dominant_skew(raw):
    """Median text-line angle (degrees, -45..45) of confident readings."""
    import math
    angles = []
    for row in raw:
        box = row.get('box')
        if not box or len(str(row.get('text', '')).strip()) < 3 or float(row.get('score', 0)) < tuning('ocr_core.line_token_min_score'):
            continue
        dx, dy = box[1][0] - box[0][0], box[1][1] - box[0][1]
        angles.append((math.degrees(math.atan2(dy, dx)) + 45) % 90 - 45)
    return float(np.median(angles)) if angles else 0.


def unstraighten_box(box, inverse):
    points = np.asarray(box, dtype=np.float64)
    return (np.column_stack((points, np.ones(len(points)))) @ inverse.T).tolist()


def restore_box(box, turns, processed_shape, original_shape, inverse=None):
    """Undo np.rot90, resize (pixel centres), and optional deskew affine."""
    ph, pw = processed_shape[:2]
    oh, ow = original_shape[:2]
    points = np.asarray(box, dtype=np.float64).copy()
    x, y = points[:, 0].copy(), points[:, 1].copy()
    if turns == 1:
        points[:, 0], points[:, 1] = pw - 1 - y, x
    elif turns == 2:
        points[:, 0], points[:, 1] = pw - 1 - x, ph - 1 - y
    elif turns == 3:
        points[:, 0], points[:, 1] = y, ph - 1 - x
    points[:, 0] = (points[:, 0] + .5) * ow / pw - .5
    points[:, 1] = (points[:, 1] + .5) * oh / ph - .5
    if inverse is not None:
        points = np.column_stack((points, np.ones(len(points)))) @ inverse.T
    return points.tolist()


def line_tokens(text, score, rotation, mode, box):
    """Preserve recognised spaced part syntax; otherwise split printed tokens."""
    if origin_exclusion(text):
        key = normalize(text)
        return [dict(text=text, key=key, raw_text=text, score=float(score),
                     rotation=rotation, mode=mode, box=box, origin_metadata=True)]
    joined = joined_line_marking(text)
    if joined:
        return [dict(text=joined, key=joined, raw_text=text, whitespace_joined=True,
                     score=float(score), rotation=rotation, mode=mode, box=box)]
    rows = []
    for token in re.findall(r'\b(?:MADE\s+IN|ASSEMBLED\s+IN|PRODUCT\s+OF)\b|[A-Za-z0-9][A-Za-z0-9/.-]*', text.upper()):
        key = normalize(token)
        if len(key) >= 3:
            rows.append(dict(text=token, key=key, score=float(score), rotation=rotation,
                             mode=mode, box=box, origin_metadata=bool(origin_exclusion(token))))
    return rows


def upright_order(box, tall, flipped):
    """Reorder a detector quadrilateral so point 0->1 follows the reading direction.

    RapidOCR turns tall line crops 90 degrees counter-clockwise; a 180-degree
    reading reverses the direction again. Later line re-reads rely on this order.
    """
    order = [1, 2, 3, 0] if tall else [0, 1, 2, 3]
    if flipped:
        order = order[2:] + order[:2]
    return np.asarray(box, dtype=np.float32)[order]


def warped_size(box):
    box = np.asarray(box, dtype=np.float32)
    width = int(max(np.linalg.norm(box[0]-box[1]), np.linalg.norm(box[2]-box[3])))
    height = int(max(np.linalg.norm(box[0]-box[3]), np.linalg.norm(box[1]-box[2])))
    return width, height


class ScanCancelled(Exception):
    """A superseded request stopped between inference calls."""


class OCR:
    def __init__(self, device=None, strict=False):
        from ocr_runtime import create_engine
        self.engine, self.runtime = create_engine(device,strict)
        import os
        self.targeted_original = os.environ.get('ICOCR_TARGETED_ORIGINAL', '1') != '0'
        self.strict = strict
        self.last_diagnostics = {}

    def read(self, crop, preferred='Original', known=(), live=False, catalog=None):
        config = configuration(getattr(self, 'preprocessing', None))
        if config is None:
            return self._read_standard(crop, preferred, known, live, catalog)
        return self._read_configured(crop, config, known, live, catalog)

    def _prepare(self, crop, treatment):
        config = getattr(self, '_active_preprocessing', None)
        if config is None:
            return enhance(crop, treatment)
        return preprocess(crop, 'Original' if config['stage'] == 'crop' else treatment,
                          config['settings'])

    def _probe(self, crop, treatment, scale):
        """Treated crop at OCR scale. An identity treatment ('Original', or any
        crop-stage preset) is resized directly: resize(copy(x)) == resize(x).
        Other treatments run at source resolution as before (CLAHE tiles and
        blur radii are resolution dependent, so they are not reordered)."""
        config = getattr(self, '_active_preprocessing', None)
        identity = (config['stage'] == 'crop') if config is not None else treatment == 'Original'
        if (identity and crop.dtype == np.uint8 and crop.ndim == 3 and crop.shape[2] == 3
                and crop.size):
            return scaled(crop, scale)
        return scaled(self._prepare(crop, treatment), scale)

    def _verify_cuda(self, message):
        if self.runtime['device'] == 'cuda':
            from ocr_runtime import providers
            active = providers(self.engine)
            if not all(v and v[0] == 'CUDAExecutionProvider' for v in active.values()):
                raise RuntimeError(message)
            self.runtime['providers'] = active

    def _cpu_fallback(self, perform):
        """Run ``perform``; on a CUDA failure (not strict) rebuild on CPU and run
        it once more. Shared by the standard and configured scans (0.8.4.3).
        Only ONNX Runtime/CUDA execution errors trigger the fallback (0.8.8);
        input errors such as ValueError are re-raised and keep the GPU session."""
        from ocr_runtime import runtime_errors
        try:
            return perform()
        except ScanCancelled:
            raise
        except runtime_errors() as exc:
            if self.runtime['device'] != 'cuda' or self.strict:
                raise
            from ocr_runtime import create_engine
            import logging
            logging.exception('CUDA scan failed; retrying once on CPU')
            self.engine = None
            self.engine, self.runtime = create_engine('cpu')
            self.runtime['label'] = 'CPU (GPU runtime fallback)'
            self.runtime['reason'] = str(exc)
            return perform()

    def _read_configured(self, crop, config, known, live, catalog):
        from scan_result import build_scan_result
        from snapshot_selection import replacement_reason, stop_reason, stage, VERSION as SELECTION_VERSION
        started = time.monotonic()
        self._live_deadline = started + getattr(self, 'live_retry_budget', tuning('ocr_core.live_retry_budget_seconds')) if live else None
        self._active_preprocessing = config

        def perform():
            self._extra_pass = False
            self._budget_limited = False
            self._timings = {'preprocessing_ms': 0., 'matching_ms': 0., 'ocr_passes': []}
            self._pass_serial = 0
            self._crop_detection_cache = {} if config['stage'] == 'crop' and getattr(self, 'fast', False) else None
            attempts = []
            winner = None
            stopped = 'exhausted'
            for index, preset in enumerate(config['presets']):
                self.check_cancelled()
                if index and self.extra_budget_expired():
                    self._budget_limited = True
                    break
                self._extra_pass = bool(index)
                pass_started = time.perf_counter()
                with recognition_preprocessing(self.engine, preset, config['settings'], config['stage'] == 'crop'):
                    rows, _ = self._read(crop, known=known, treatment=preset,
                                         allow_deskew=config['stage'] == 'snapshot')
                self.check_cancelled()
                self._verify_cuda('OCR session switched to CPU during the preprocessing experiment')
                diagnostics = self.last_diagnostics
                match_started = time.perf_counter()
                decision = build_scan_result(rows, diagnostics.get('all_candidates', rows), catalog)
                self._timings['matching_ms'] += (time.perf_counter()-match_started)*1000
                reason = stop_reason(decision)
                success = bool(reason)
                replacement = ('first attempt' if winner is None else
                               replacement_reason(winner[1], decision))
                attempts.append(dict(preset=preset, accepted=success,
                    stop_reason=reason, replacement_reason=replacement or 'incumbent retained',
                    stage=stage(decision, diagnostics.get('raw', [])),
                    scan_result=decision, raw=diagnostics.get('raw', []),
                    milliseconds=(time.perf_counter()-pass_started)*1000,
                    selected_text=(decision.get('selected') or {}).get('text', ''),
                    partnumber=((decision.get('selected') or {}).get('selected_database_match') or {}).get('part', ''),
                    ocr_calls=diagnostics.get('ocr_calls', 0),
                    detection_reused=diagnostics.get('detection_reused', 0)))
                if replacement:
                    winner = (diagnostics, decision, preset)
                if success or config['mode'] == 'single':
                    stopped = reason or 'single_attempt'
                    break
                # Crop-only retries cannot discover text absent from the fixed detector input.
                if self._crop_detection_cache is not None and not any(v[2] for v in self._crop_detection_cache.values()):
                    stopped = 'no_detected_crops'
                    break
            return attempts, winner, stopped
        try:
            attempts, winner, stopped = self._cpu_fallback(perform)
            diagnostics, decision, preset = winner
            diagnostics['scan_result'] = decision
            diagnostics['note'] = 'Attempt evidence retained separately; repeated transforms do not add votes or increase confidence. Selected attempt supplies display/raw output. Crop transform time is included in recognition time.'
            diagnostics['raw_observations'] = diagnostics.get('raw', [])
            diagnostics['raw'] = deduplicate_raw_lines(diagnostics['raw_observations'])
            diagnostics['preprocessing'] = dict(config, version=PREPROCESSING_VERSION,
                attempts=attempts, selected_preset=preset, selection_version=SELECTION_VERSION,
                stage=stage(decision, diagnostics.get('raw', [])),
                stop_reason='budget' if self._budget_limited else stopped)
            diagnostics['retry_calls'] = len(attempts)-1
            diagnostics['ocr_calls'] = sum(a['ocr_calls'] for a in attempts)
            diagnostics['live_budget_limited'] = self._budget_limited
            self._timings['total_ms'] = (time.monotonic()-started)*1000
            diagnostics['timings'] = self._timings
            diagnostics['runtime'] = self.runtime
            self.last_diagnostics = diagnostics
            return decision['display_candidates'], time.monotonic()-started
        finally:
            self._active_preprocessing = None
            self._crop_detection_cache = None
            self._extra_pass = False

    def _read_standard(self, crop, preferred='Original', known=(), live=False, catalog=None):
        started = time.monotonic()
        self._live_deadline = started + getattr(self, 'live_retry_budget', tuning('ocr_core.live_retry_budget_seconds')) if live else None
        self._extra_pass = False
        self._budget_limited = False
        self.check_cancelled()
        hint = getattr(self, '_live_turn', None) if live else None
        orientations = ([hint] + [t for t in range(4) if t != hint]
                        if hint is not None else list(range(4)))
        self._timings = {'preprocessing_ms': 0., 'matching_ms': 0., 'ocr_passes': []}
        self._pass_serial = 0
        selection_cache = {}
        def choices(result):
            from scan_result import build_scan_result
            diagnostics = self.last_diagnostics
            if selection_cache.get('diagnostics') is not diagnostics:
                start = time.perf_counter()
                previous = diagnostics.get('prior_selection')
                initial = diagnostics.get('initial_observations')
                if previous is None and initial:
                    # build_scan_result reads only the ids of the eligible rows.
                    eligible, _, every = split_candidates(initial, known, modes=1, copy=False)
                    previous = build_scan_result(eligible, every, catalog)['selected']
                selection_cache['result'] = build_scan_result(
                    result[0], diagnostics.get('all_candidates', result[0]), catalog, previous=None if getattr(self, 'verification', False) else previous)
                selection_cache['diagnostics'] = diagnostics
                self._timings['matching_ms'] += (time.perf_counter()-start)*1000
            return selection_cache['result']['candidates']
        def early_accept(rows):
            from component_catalog import live_candidates
            start = time.perf_counter()
            selected = live_candidates(rows, catalog)
            self._timings['matching_ms'] += (time.perf_counter()-start)*1000
            if not selected:
                return False
            best = selected[0]
            # With a catalogue, unmatched/date/partial readings must still search
            # the other rotations for a real part number.
            if catalog is not None:
                if hint is not None and best['rotation'] == hint*90 and best.get('selected_database_match'):
                    return best['score'] >= tuning('ocr_core.database_early_accept_score')
                return best['score'] >= tuning('ocr_core.structured_early_accept_score') and any(
                    m.get('match_type') == 'exact' for m in best['database_matches'])
            return best['score'] >= tuning('ocr_core.family_early_accept_score') and best.get('kind') in ('family', 'saved', 'numeric')

        # 'Live' is a request label, not an image treatment. Standard scanning
        # starts with Original; explicit Local contrast preferences still work.
        primary = 'Original' if preferred in ('Original', 'Live') else 'Local contrast'
        fast_options = {'treatment': primary}
        if live and not getattr(self, 'verification', False):
            fast_options['early_accept'] = early_accept
        if live and getattr(self, 'targeted_original', False):
            fast_options['treatment'] = ('Original' if getattr(self, 'live_primary_original', True)
                                         else 'Local contrast')
        def perform():
            self._extra_pass = False
            result = self._read(crop,preferred,known,orientations=orientations,**fast_options)
            selected = choices(result)
            # Strong unknown/custom text is a successful read, too. One extra
            # treatment is the retry budget; targeted Original covers all axes.
            strong = any(r.get('score', 0) >= (tuning('ocr_core.exact_retry_stop_score') if any(
                m.get('match_type') == 'exact' for m in r['database_matches']) else tuning('ocr_core.other_retry_stop_score'))
                         for r in selected)
            base = self.last_diagnostics
            decision = selection_cache['result']
            unresolved = any(r.get('conflicts') and not r.get('database_identity_consistent') and
                             r.get('kind') in ('family', 'unknown') and r.get('score', 0) >= tuning('ocr_core.retry_conflict_score') and
                             not r.get('orientation_alternative') and not r.get('exclusion_reason')
                             for r in decision['all_candidates'])
            targeted = bool(getattr(self, 'targeted_original', False) and
                            (not decision['selected'] or unresolved))
            needs_retry = (not strong or targeted) and 'observations' in base
            if live and getattr(self, 'acquisition_only', False):
                needs_retry = False
                self.last_diagnostics['acquisition_only'] = True
            # 0.8.3.4: inside a body-crop pass with nothing selected, the full-
            # selection recovery (body_scan) follows and runs its own retry, so
            # this one would duplicate it (8 OCR passes instead of 6).
            if needs_retry and getattr(self, 'defer_retry', False) and not decision['selected']:
                needs_retry = False
                self.last_diagnostics['retry_deferred'] = True
            if needs_retry and self.extra_budget_expired():
                self._budget_limited = True
            if needs_retry and not self.extra_budget_expired():
                from component_catalog import automatic_exclusion, annotate
                evidence = [r for r in base.get('all_candidates', [])
                            if not automatic_exclusion(r['key']) and
                            (numeric_marking(r['key']) or
                             (any(c.isalpha() for c in r['key']) and any(c.isdigit() for c in r['key'])))]
                evidence = annotate(evidence, catalog)
                best = max(evidence, key=lambda r: (
                    bool(r.get('trusted_database_matches')) and r.get('score', 0) >= tuning('ocr_core.database_pending_score'),
                    any(m.get('match_type') == 'exact' for m in r['database_matches']),
                    r.get('score', 0)), default=None)
                turn = best['rotation'] // 90 if best else (hint or 0)
                treatment = 'Original' if best and best.get('score', 0) >= tuning('ocr_core.original_retry_score') else 'Lighting correction'
                if treatment == fast_options['treatment']:
                    treatment = 'Local contrast'
                retry_turns = [turn]
                if targeted:
                    treatment = 'Local contrast' if fast_options.get('treatment') == 'Original' else 'Original'
                    retry_turns = list(range(4))
                self._extra_pass = True
                self._read(crop, preferred, known, orientations=retry_turns,
                           treatment=treatment, allow_deskew=False)
                retry = self.last_diagnostics
                observations = base['observations'] + retry['observations']
                rows, angle, every = split_candidates(observations, known, modes=1)
                self.last_diagnostics = dict(base,
                    raw=base['raw'] + retry['raw'], observations=observations,
                    prior_selection=decision['selected'],
                    all_candidates=every,
                    candidates=rows, selected_rotation=angle,
                    treatments=base['treatments'] + [treatment],
                    ocr_calls=base['ocr_calls'] + retry['ocr_calls'], retry_calls=1,
                    targeted_original=targeted,
                    retry_reason=('identifier_conflict' if unresolved else 'no_selection') if targeted else 'weak_selection',
                    retry_detection_passes=retry['ocr_calls'],
                    note='One retry treatment; alternate-treatment fallback covers both text axes when enabled.')
                result = rows, result[1]
            else:
                self.last_diagnostics['retry_calls'] = 0
                self.last_diagnostics['targeted_original'] = False
            return straighten_fallback(result)
        def straighten_fallback(result):
            """0.8.3.4: one straightened read when nothing is selected and the
            detected lines lean 8-43 degrees (fast mode never deskews)."""
            if (getattr(self, 'acquisition_only', False) or
                    not getattr(self, 'fast', False) or getattr(self, 'defer_retry', False) or
                    os.environ.get('ICOCR_STRAIGHTEN_FALLBACK', '1') == '0'):
                return result
            choices(result)
            if selection_cache['result']['selected'] or self.extra_budget_expired():
                return result
            base = self.last_diagnostics
            skew = dominant_skew(base.get('raw', []))
            if not 8 < abs(skew) < 43:
                return result
            straight, matrix = straighten(crop, skew, return_matrix=True)
            inverse = cv2.invertAffineTransform(matrix)
            self._extra_pass = True
            self._read(straight, preferred, known, orientations=orientations,
                       treatment=fast_options.get('treatment', 'Local contrast'), allow_deskew=False)
            tilted = self.last_diagnostics
            for row in tilted['raw'] + tilted['observations']:
                if row.get('box'):
                    row['box'] = unstraighten_box(row['box'], inverse)
                row['deskew_degrees'] = skew
            observations = base['observations'] + tilted['observations']
            rows, angle, every = split_candidates(observations, known, modes=1)
            self.last_diagnostics = dict(base,
                raw=base['raw'] + tilted['raw'], observations=observations,
                all_candidates=every,
                candidates=rows, selected_rotation=angle, deskew_degrees=skew,
                ocr_calls=base.get('ocr_calls', 0) + tilted.get('ocr_calls', 0),
                straightened_fallback=dict(degrees=skew, detection_passes=tilted.get('ocr_calls', 0)))
            return rows, result[1]
        def checked():
            result = perform()
            self._verify_cuda('OCR session switched to CPU during the scan')
            return result
        result = self._cpu_fallback(checked)
        selected = choices(result)
        final = selection_cache['result']
        if live and selected and (catalog is None or selected[0].get('selected_database_match')):
            self._live_turn = selected[0]['rotation'] // 90
        self.last_diagnostics['raw_observations'] = self.last_diagnostics.get('raw', [])
        self.last_diagnostics['raw'] = deduplicate_raw_lines(self.last_diagnostics['raw_observations'])
        self.last_diagnostics['raw_note'] = ('Repeated readings of the same text region merged within rotation/treatment; '
            'all individual readings retained in raw_observations.')
        self.last_diagnostics['scan_result'] = final
        self.last_diagnostics['configuration'] = configuration_diagnostics()
        self._timings['total_ms'] = (time.monotonic()-started)*1000
        self.last_diagnostics['timings'] = self._timings
        self.last_diagnostics['live_budget_limited'] = self._budget_limited
        result = (final['display_candidates'], result[1])
        self.last_diagnostics['runtime']=self.runtime
        return result[0], time.monotonic()-started

    def check_cancelled(self):
        callback = getattr(self, 'cancelled', None)
        if callback is not None and callback():
            raise ScanCancelled()

    def extra_budget_expired(self):
        deadline = getattr(self, '_live_deadline', None)
        return deadline is not None and time.monotonic() >= deadline

    def _read(self, crop, preferred='Original', known=(), orientations=range(4),
              treatment='Local contrast', allow_deskew=True, early_accept=None):
        if getattr(self, 'fast', False):
            return self._read_fast(crop, known, orientations=orientations,
                                   treatment=treatment, early_accept=early_accept)
        return self._read_full(crop, preferred, known, orientations=orientations,
                               treatment=treatment, allow_deskew=allow_deskew,
                               early_accept=early_accept)

    def _detect_turn(self, image, k, cache=None):
        """Text detection on one quarter turn (no classifier, no recognition).

        Returns ((prepared, record, boxes, crops, origin), milliseconds, reused).
        ``origin`` holds the detector quadrilaterals in ``image`` coordinates.
        """
        if cache is not None and k in cache:
            return cache[k], 0., True
        engine = self.engine
        det_start = time.perf_counter()
        prepared, ratio_h, ratio_w = engine.preprocess(image)
        record = {'preprocess': {'ratio_h': ratio_h, 'ratio_w': ratio_w}}
        prepared, record = engine.maybe_add_letterbox(prepared, record)
        boxes, _ = engine.auto_text_det(prepared)
        crops = engine.get_crop_img_list(prepared, boxes) if boxes else []
        origin = engine._get_origin_points(boxes, record, image.shape[0], image.shape[1]) if boxes else []
        entry = (prepared, record, boxes, crops, origin)
        if cache is not None:
            cache[k] = entry
        return entry, (time.perf_counter()-det_start)*1000, False

    def _upright_gate(self, crops):
        """Indices of line crops the angle classifier confidently calls upright.

        0.8.4.3 (tuning ``ocr_core.cls_gate_enabled``): the 180-degree re-read of
        such a line is skipped only if its upright reading is also strong (see
        _recognise_both). Off, or for engines without a classifier: no gate.
        """
        if not crops or not _setting('ocr_core.cls_gate_enabled', 0):
            return []
        try:
            _, labels, _ = self.engine.text_cls(crops)
            minimum = float(_setting('ocr_core.cls_gate_min_cls_score', .98))
            gate = [i for i, (label, score) in enumerate(labels)
                    if str(label) == '0' and float(score) >= minimum]
        except (TypeError, ValueError, AttributeError, IndexError):
            return []
        return gate if len(labels) == len(crops) else []

    def _recognise_both(self, crops):
        """[(upright, flipped)] for every line crop, and the number of skipped
        reverse reads. ``flipped`` is None when the classifier gate skipped it.
        Without a gate this is the historical single batched call."""
        engine = self.engine
        count = len(crops)
        reverse = [np.ascontiguousarray(np.rot90(c, 2)) for c in crops]
        gate = set() if getattr(self, 'verification', False) else set(self._upright_gate(crops))
        if not gate:
            results, _ = engine.text_rec(crops + reverse)
            return [(results[i], results[i+count]) for i in range(count)], 0
        first = [i for i in range(count) if i not in gate]
        results, _ = engine.text_rec(crops + [reverse[i] for i in first])
        flipped = [None]*count
        for j, i in enumerate(first):
            flipped[i] = results[count+j]
        upright = results[:count]
        minimum = float(_setting('ocr_core.cls_gate_min_rec_score', .97))
        second = [i for i in sorted(gate) if float(upright[i][1]) < minimum]
        if second:
            more, _ = engine.text_rec([reverse[i] for i in second])
            for j, i in enumerate(second):
                flipped[i] = more[j]
        return list(zip(upright, flipped)), count - len(first) - len(second)

    def _line_readings(self, boxes, crops, origin, k, threshold):
        """Both reading directions of each detected line, labelled with the
        quarter turn that makes it upright (k: detection turn of ``origin``)."""
        pairs, skipped = self._recognise_both(crops)
        readings = []
        for i, (upright, flipped) in enumerate(pairs):
            winner_flipped = flipped is not None and float(flipped[1]) > float(upright[1])
            width, height = warped_size(boxes[i])
            tall = width > 0 and height / width >= 1.5
            # Both directions have already been inferred. Keep alternatives
            # for catalogue selection instead of losing a valid lower score.
            for reverse, reading in ((False, upright), (True, flipped)):
                if reading is None:
                    continue
                text, score = reading[:2]
                if not text or float(score) < threshold:
                    continue
                row = dict(crop_id=i, text=text, score=float(score),
                           rotation=((k + (1 if tall else 0) + (2 if reverse else 0)) % 4) * 90,
                           alternative=reverse != winner_flipped,
                           box=upright_order(origin[i], tall, reverse), det_box=origin[i])
                if flipped is None:
                    row['reverse_read_skipped'] = True
                readings.append(row)
        return readings, skipped

    def _read_fast(self, crop, known=(), orientations=range(4), treatment='Local contrast',
                   early_accept=None):
        """Detect lines at 0 and 90 degrees only; recognise every line both ways.

        Text detection is the expensive stage and covers 180/270 degrees through
        the 180-degree re-read of each line. Line crops are perspective-warped,
        so no separate deskew pass is made. Requested orientations only choose
        which detection turns run (and in which order).
        """
        start = time.monotonic()
        h, w = crop.shape[:2]
        if min(h, w) < 12:
            raise ValueError('Select a larger region around the IC.')
        timings = getattr(self, '_timings', None)
        scale = min(2.0, 1400/max(h, w))
        prep_start = time.perf_counter()
        probe = self._probe(crop, treatment, scale)
        if timings is not None:
            timings['preprocessing_ms'] += (time.perf_counter()-prep_start)*1000
        turns_order = []
        for turn in orientations:
            if turn % 2 not in turns_order:
                turns_order.append(turn % 2)
        engine = self.engine
        threshold = float(getattr(engine, 'text_score', .5))
        observations, raw = [], []
        ocr_calls = 0
        lines = 0
        detection_reused = 0
        skipped_reverse = 0
        def finish(note, early=False):
            rows, angle, every = split_candidates(observations, known, modes=1)
            self.last_diagnostics = dict(raw=raw, observations=observations,
                all_candidates=every,
                selected_rotation=angle, deskew_degrees=0., treatments=[treatment],
                candidates=rows, ocr_calls=ocr_calls, early_exit=early, fast=True,
                lines=lines, detection_reused=detection_reused, note=note)
            if skipped_reverse:
                self.last_diagnostics['reverse_reads_skipped'] = skipped_reverse
            return rows, time.monotonic()-start
        for k in turns_order:
            self.check_cancelled()
            if ocr_calls and getattr(self, '_extra_pass', False) and self.extra_budget_expired():
                self._budget_limited = True
                break
            image = np.ascontiguousarray(np.rot90(probe, k))
            self._pass_serial = getattr(self, '_pass_serial', 0) + 1
            pass_id = self._pass_serial
            (prepared, record, boxes, crops, origin), det_ms, reused = self._detect_turn(
                image, k, getattr(self, '_crop_detection_cache', None))
            if reused:
                detection_reused += 1
            else:
                ocr_calls += 1
            rec_ms = 0.
            if boxes:
                self.check_cancelled()
                rec_start = time.perf_counter()
                readings, skipped = self._line_readings(boxes, crops, origin, k, threshold)
                skipped_reverse += skipped
                rec_ms = (time.perf_counter()-rec_start)*1000
                lines += len(crops)
                for reading in readings:
                    text, score, rotation = reading['text'], reading['score'], reading['rotation']
                    alternative, i = reading['alternative'], reading['crop_id']
                    mapped = restore_box(reading['box'], k, probe.shape, crop.shape)
                    row = dict(text=text, score=score, rotation=rotation,
                               mode=treatment, orientation_alternative=alternative,
                               box=mapped, detection_turn=k*90, pass_id=pass_id,
                               crop_id=i, deskew_degrees=0.)
                    if reading.get('reverse_read_skipped'):
                        row['reverse_read_skipped'] = True
                    raw.append(row)
                    tokens = line_tokens(text, score, rotation, treatment, mapped)
                    for token in tokens:
                        token.update(orientation_alternative=alternative, pass_id=pass_id,
                                     crop_id=i, detection_turn=k*90, deskew_degrees=0.)
                    observations.extend(tokens)
            if timings is not None:
                timings['ocr_passes'].append(dict(rotation=k*90, treatment=treatment, deskew=False,
                    milliseconds=det_ms+rec_ms, detection_ms=det_ms, recognition_ms=rec_ms,
                    lines=len(boxes) if boxes else 0))
            if early_accept is not None and k != turns_order[-1]:
                rows, _ = select_candidates(observations, known, modes=1)
                if early_accept(rows):
                    return finish('Live fast scan stopped after a confident reading at one '
                                  'detection turn.', early=True)
        return finish('Fast scan: detection at 0/90 degrees, each line read both ways. '
                      'Single-treatment readings are tentative.')

    def warm_up(self):
        """Run detection and recognition once so the first real scan is not slowed
        by ONNX Runtime's lazy initialisation."""
        image = np.full((96, 320, 3), 200, np.uint8)
        cv2.putText(image, 'LM2904', (12, 64), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (20, 20, 20), 3)
        self.engine(image)
        self.engine.text_rec([image[20:80]])

    def read_line(self, image, box, treatment='Local contrast', both_directions=True):
        """Recognition only, on one known text line (live refinement; no detection).

        The box is in image coordinates with point 0->1 along the reading direction.
        Both directions are read; the stronger reading is returned.
        """
        started = time.perf_counter()
        box = np.asarray(box, dtype=np.float32)
        h, w = image.shape[:2]
        width, height = warped_size(box)
        if width < 6 or height < 4:
            return None
        margin = max(8., .5*height)
        lo = np.maximum(np.floor(box.min(axis=0)-margin), 0).astype(int)
        hi = np.minimum(np.ceil(box.max(axis=0)+margin), [w, h]).astype(int)
        if np.any(hi-lo < 4):
            return None
        region = enhance(image[lo[1]:hi[1], lo[0]:hi[0]], treatment)
        factor = float(np.clip(56./height, 1., 4.))
        size = (max(8, int(round(width*factor))), max(8, int(round(height*factor))))
        target = np.array([[0, 0], [size[0], 0], [size[0], size[1]], [0, size[1]]], np.float32)
        matrix = cv2.getPerspectiveTransform(box-lo.astype(np.float32), target)
        line = cv2.warpPerspective(region, matrix, size, flags=cv2.INTER_CUBIC,
                                   borderMode=cv2.BORDER_REPLICATE)
        inputs = [line, np.ascontiguousarray(np.rot90(line, 2))] if both_directions else [line]
        results, _ = self.engine.text_rec(inputs)
        if not both_directions:
            text, score = results[0][:2]
            return dict(text=text, score=float(score), flipped=False, alternatives=[],
                        milliseconds=(time.perf_counter()-started)*1000)
        upright, flipped = results[0], results[1]
        reverse = float(flipped[1]) > float(upright[1])
        text, score = (flipped if reverse else upright)[:2]
        return dict(text=text, score=float(score), flipped=reverse,
                    alternatives=[dict(text=t, score=float(s)) for t, s, *rest in results],
                    milliseconds=(time.perf_counter()-started)*1000)

    def _read_full(self, crop, preferred='Original', known=(), orientations=range(4),
              treatment='Local contrast', allow_deskew=True, early_accept=None):
        # 0.8.4.3: shared 0/90-degree detection (tuning ocr_core.full_shared_detection).
        # Engines without RapidOCR's stage methods (test doubles) keep the legacy path.
        if (_setting('ocr_core.full_shared_detection', 0) and
                callable(getattr(type(self.engine), 'auto_text_det', None))):
            return self._read_full_shared(crop, known, orientations=orientations,
                                          treatment=treatment, allow_deskew=allow_deskew,
                                          early_accept=early_accept)
        start = time.monotonic()
        h,w = crop.shape[:2]
        if min(h,w) < 12:
            raise ValueError('Select a larger region around the IC.')
        modes = [treatment]
        scale = min(2.0,1400/max(h,w))
        observations = []
        raw = []
        # Estimate the dominant text baseline; quadrants alone do not fix diagonal chips.
        import math
        angles = []
        prep_start = time.perf_counter()
        probe = self._probe(crop, treatment, scale)
        if hasattr(self, '_timings'):
            self._timings['preprocessing_ms'] += (time.perf_counter()-prep_start)*1000
        ocr_calls = 0
        for turns in orientations:
            self.check_cancelled()
            if ocr_calls and getattr(self, '_extra_pass', False) and self.extra_budget_expired():
                self._budget_limited = True
                break
            call_start = time.perf_counter()
            probe_rows,_ = self.engine(np.ascontiguousarray(np.rot90(probe,turns)))
            if hasattr(self, '_timings'):
                self._timings['ocr_passes'].append(dict(rotation=turns*90, treatment=treatment,
                    deskew=False, milliseconds=(time.perf_counter()-call_start)*1000))
            ocr_calls += 1
            self._pass_serial = getattr(self, '_pass_serial', 0) + 1
            for crop_id, (box, text, score) in enumerate(probe_rows or []):
                mapped = restore_box(box, turns, probe.shape, crop.shape)
                provenance = dict(pass_id=self._pass_serial, crop_id=crop_id,
                                  detection_turn=turns*90, deskew_degrees=0.)
                raw.append(dict(text=text, score=float(score), rotation=turns*90,
                                mode=treatment, box=mapped, **provenance))
                observations.extend(dict(t, **provenance) for t in
                                    line_tokens(text, score, turns*90, treatment, mapped))
            if early_accept is not None:
                # Retain evidence from all orientations already examined, including
                # conflicting spellings, before deciding to stop the search.
                fast_observations = list(observations)
                fast_raw = list(raw)
                fast_rows, fast_angle, fast_all = split_candidates(fast_observations, known, modes=1)
                if early_accept(fast_rows):
                    self.last_diagnostics = dict(raw=fast_raw,observations=fast_observations,
                        all_candidates=fast_all,
                        selected_rotation=fast_angle,deskew_degrees=0,treatments=modes,
                        candidates=fast_rows,ocr_calls=ocr_calls,early_exit=True,
                        note='Live scan stopped after a confident reading; unused rotations skipped.')
                    return fast_rows,time.monotonic()-start
            for box,text,score in probe_rows or []:
                if len(text) < 4 or float(score) < tuning('ocr_core.recheck_min_score'):
                    continue
                dx,dy = box[1][0]-box[0][0],box[1][1]-box[0][1]
                angle = (math.degrees(math.atan2(dy,dx))+45)%90-45
                angles.append(angle)
        skew = float(np.median(angles)) if angles else 0.0
        initial_observations = list(observations)
        inverse = None
        if allow_deskew and 8 < abs(skew) < 43 and self.extra_budget_expired():
            self._budget_limited = True
        if allow_deskew and 8 < abs(skew) < 43 and not self.extra_budget_expired():
            prep_start = time.perf_counter()
            crop, matrix = straighten(crop,skew,return_matrix=True)
            inverse = cv2.invertAffineTransform(matrix)
            if hasattr(self, '_timings'):
                self._timings['preprocessing_ms'] += (time.perf_counter()-prep_start)*1000
        else:
            skew = 0.0
        for mode in modes:
            if skew != 0.0:
                prep_start = time.perf_counter()
                im = self._probe(crop, mode, scale)
                if hasattr(self, '_timings'):
                    self._timings['preprocessing_ms'] += (time.perf_counter()-prep_start)*1000
            for turns in orientations:
                self.check_cancelled()
                if skew and self.extra_budget_expired():
                    self._budget_limited = True
                    break
                if skew == 0.0:
                    continue  # Uncorrected probe evidence already retained.
                else:
                    call_start = time.perf_counter()
                    rows,_ = self.engine(np.ascontiguousarray(np.rot90(im,turns)))
                    if hasattr(self, '_timings'):
                        self._timings['ocr_passes'].append(dict(rotation=turns*90, treatment=mode,
                            deskew=True, milliseconds=(time.perf_counter()-call_start)*1000))
                    ocr_calls += 1
                    self._pass_serial = getattr(self, '_pass_serial', 0) + 1
                for crop_id, (box,text,score) in enumerate(rows or []):
                    mapped_box = restore_box(box, turns, (im if skew else probe).shape, crop.shape, inverse)
                    raw.append(dict(text=text,score=float(score),rotation=turns*90,mode=mode,
                                    box=mapped_box, detection_turn=turns*90,
                                    pass_id=self._pass_serial, crop_id=crop_id, deskew_degrees=skew))
                    observations.extend(dict(t, pass_id=self._pass_serial, crop_id=crop_id,
                                             detection_turn=turns*90, deskew_degrees=skew)
                                        for t in line_tokens(text, score, turns*90, mode, mapped_box))
        candidates, angle, every = split_candidates(observations, known, len(modes))
        self.last_diagnostics = dict(raw=raw, observations=observations,
             initial_observations=initial_observations if skew else [],
             all_candidates=every, selected_rotation=angle, deskew_degrees=skew,
             treatments=modes, candidates=candidates, ocr_calls=ocr_calls,
             note=treatment + ' only. Single-treatment readings are tentative; rotations are not independent evidence.')
        return candidates,time.monotonic()-start

    def _read_full_shared(self, crop, known=(), orientations=range(4), treatment='Local contrast',
                          allow_deskew=True, early_accept=None):
        """Full scan with the fast scan's detection sharing (0.8.4.3).

        RapidOCR's own pipeline runs its angle classifier, which turns crops it
        believes are upside down; the 180/270-degree detection passes then read
        the same lines as 0/90 under a wrong rotation label (an upside-down chip
        read at all four rotations). Here detection runs at 0 and 90 degrees
        with no classifier and every line is recognised both ways, so each
        reading carries the rotation that actually makes it upright and two of
        the four detection passes are saved. Deskew is unchanged.
        """
        import math
        start = time.monotonic()
        h, w = crop.shape[:2]
        if min(h, w) < 12:
            raise ValueError('Select a larger region around the IC.')
        modes = [treatment]
        scale = min(2.0, 1400/max(h, w))
        observations, raw, angles = [], [], []
        timings = getattr(self, '_timings', None)
        prep_start = time.perf_counter()
        probe = self._probe(crop, treatment, scale)
        if timings is not None:
            timings['preprocessing_ms'] += (time.perf_counter()-prep_start)*1000
        turns_order = []
        for turn in orientations:
            if turn % 2 not in turns_order:
                turns_order.append(turn % 2)
        threshold = float(getattr(self.engine, 'text_score', .5))
        ocr_calls = 0
        skipped_reverse = 0

        def scan(image, k, source_shape, inverse, skew):
            nonlocal ocr_calls, skipped_reverse
            (prepared, record, boxes, crops, origin), det_ms, _ = self._detect_turn(
                np.ascontiguousarray(np.rot90(image, k)), k)
            rec_start = time.perf_counter()
            readings, skipped = (self._line_readings(boxes, crops, origin, k, threshold)
                                 if boxes else ([], 0))
            skipped_reverse += skipped
            rec_ms = (time.perf_counter()-rec_start)*1000
            if timings is not None:
                timings['ocr_passes'].append(dict(rotation=k*90, treatment=treatment,
                    deskew=bool(skew), milliseconds=det_ms+rec_ms, detection_ms=det_ms,
                    recognition_ms=rec_ms, lines=len(boxes) if boxes else 0))
            ocr_calls += 1
            self._pass_serial = getattr(self, '_pass_serial', 0) + 1
            for reading in readings:
                text, score, rotation = reading['text'], reading['score'], reading['rotation']
                mapped = restore_box(reading['box'], k, image.shape, source_shape, inverse)
                provenance = dict(pass_id=self._pass_serial, crop_id=reading['crop_id'],
                                  detection_turn=k*90, deskew_degrees=skew,
                                  orientation_alternative=reading['alternative'])
                row = dict(text=text, score=score, rotation=rotation, mode=treatment,
                           box=mapped, **provenance)
                if reading.get('reverse_read_skipped'):
                    row['reverse_read_skipped'] = True
                raw.append(row)
                observations.extend(dict(t, **provenance) for t in
                                    line_tokens(text, score, rotation, treatment, mapped))
            return readings

        for k in turns_order:
            self.check_cancelled()
            if ocr_calls and getattr(self, '_extra_pass', False) and self.extra_budget_expired():
                self._budget_limited = True
                break
            readings = scan(probe, k, crop.shape, None, 0.)
            if early_accept is not None:
                fast_rows, fast_angle, fast_all = split_candidates(list(observations), known, modes=1)
                if early_accept(fast_rows):
                    self.last_diagnostics = dict(raw=list(raw), observations=list(observations),
                        all_candidates=fast_all, selected_rotation=fast_angle, deskew_degrees=0,
                        treatments=modes, candidates=fast_rows, ocr_calls=ocr_calls,
                        early_exit=True, shared_detection=True,
                        note='Live scan stopped after a confident reading; unused rotations skipped.')
                    return fast_rows, time.monotonic()-start
            for reading in readings:
                if (reading['alternative'] or len(reading['text']) < 4 or
                        reading['score'] < tuning('ocr_core.recheck_min_score')):
                    continue
                box = reading['det_box']
                dx, dy = box[1][0]-box[0][0], box[1][1]-box[0][1]
                angles.append((math.degrees(math.atan2(dy, dx))+45) % 90-45)
        skew = float(np.median(angles)) if angles else 0.0
        initial_observations = list(observations)
        if allow_deskew and 8 < abs(skew) < 43 and self.extra_budget_expired():
            self._budget_limited = True
        if allow_deskew and 8 < abs(skew) < 43 and not self.extra_budget_expired():
            prep_start = time.perf_counter()
            straight, matrix = straighten(crop, skew, return_matrix=True)
            inverse = cv2.invertAffineTransform(matrix)
            image = self._probe(straight, treatment, scale)
            if timings is not None:
                timings['preprocessing_ms'] += (time.perf_counter()-prep_start)*1000
            for k in turns_order:
                self.check_cancelled()
                if self.extra_budget_expired():
                    self._budget_limited = True
                    break
                scan(image, k, straight.shape, inverse, skew)
        else:
            skew = 0.0
        candidates, angle, every = split_candidates(observations, known, len(modes))
        self.last_diagnostics = dict(raw=raw, observations=observations,
             initial_observations=initial_observations if skew else [],
             all_candidates=every, selected_rotation=angle, deskew_degrees=skew,
             treatments=modes, candidates=candidates, ocr_calls=ocr_calls, shared_detection=True,
             note='Full scan: detection at 0/90 degrees without the angle classifier, each line '
                  'read both ways. Single-treatment readings are tentative; rotations are not '
                  'independent evidence.')
        if skipped_reverse:
            self.last_diagnostics['reverse_reads_skipped'] = skipped_reverse
        return candidates, time.monotonic()-start
