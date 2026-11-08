"""Line ranking for multi-line IC markings (0.8.3.3).

Step 1  marking_block():   group the recognised text into lines of one marking
                           block and order them in the text's own reading direction.
Step 2  line_features():   measurements per candidate line: position in the block,
                           text shape, database evidence, brand/logo context,
                           character height and OCR quality.
Step 3  rank():            a weighted score (conditional logit) with weights fitted
                           on annotated images (line_weights.json, written by
                           tools/fit_line_ranking.py). Diagnostics show every term.

Hard safety rules are unchanged and are applied before ranking: origin text, PCB
references, short resistor values, unresolved conflicts, unsupported reverse
readings and "trusted database evidence takes priority" (component_catalog).
Set ICOCR_LINE_RANKING=0 to use the 0.8.3.2 rule order instead.
"""
import os
import re
import numpy as np

VERSION = '1.0.0'
from config_loader import get_config, tuning
from rule_modules import rules_directory
WEIGHTS_PATH = rules_directory() / 'ranking.lines.json'
BRANDS_PATH = rules_directory() / 'ranking.brands.json'
_MODEL = get_config('ranking/line_weights.json')
_BRANDS = frozenset(w for words in get_config('rules/brands.json')['brands'].values() for w in words)
EXTENDED_MIN_SCORE = _MODEL['extended_min_score']


def enabled():
    override = os.environ.get('ICOCR_LINE_RANKING')
    return override != '0' if override is not None else _MODEL['enabled']


def brands():
    return set(_BRANDS)


def weights():
    # Preserve caller isolation without touching disk in the scan loop.
    return dict(_MODEL, weights=dict(_MODEL['weights']))


# --------------------------------------------------------------------- step 1
def _geometry(box):
    a = np.asarray(box, dtype=float)
    if a.shape != (4, 2) or not np.isfinite(a).all():
        return None
    edge = a[1] - a[0]
    width = float(np.linalg.norm(edge))
    if width < 2:
        return None
    return a, edge / width


def marking_block(rows):
    """Assign line numbers in the dominant reading direction.

    Sets on each row: block_line (0 = top line of the main block, None when not
    in it), block_lines (number of lines in the block), block_off_axis (text
    in another direction) and block_height_ratio (character height relative
    to the block median). Returns a summary for diagnostics.
    """
    geo = []
    for row in rows:
        row.update(block_line=None, block_lines=0, block_off_axis=False, block_height_ratio=1.)
        g = _geometry(row.get('box')) if row.get('box') else None
        if g is not None:
            geo.append((row, g[0], g[1]))
    if not geo:
        return dict(lines=0)
    # Dominant direction: score x length of confident, preferred-direction text.
    votes = []
    for row, a, u in geo:
        if row.get('orientation_alternative') or row.get('score', 0) < .80:
            continue
        weight = row.get('score', 0) * len(row.get('key', ''))
        for i, (v, w) in enumerate(votes):
            if float(np.dot(v, u)) > .94:
                votes[i] = (v, w + weight)
                break
        else:
            votes.append((u, weight))
    if not votes:
        return dict(lines=0)
    u = max(votes, key=lambda item: item[1])[0]
    v = np.array([-u[1], u[0]])
    aligned = []
    for row, a, ru in geo:
        # A reverse reading (180 degrees) of a line is the same physical line.
        if abs(float(np.dot(ru, u))) < .9:
            row['block_off_axis'] = True
            continue
        aligned.append((row, float((a @ v).mean()), float(np.ptp(a @ v)), a @ u))
    if not aligned:
        return dict(lines=0)
    height = float(np.median([h for _, _, h, _ in aligned])) or 1.
    # Lines: offsets closer than 0.6 x median height belong to one printed line.
    aligned.sort(key=lambda item: item[1])
    lines = []
    for item in aligned:
        if lines and item[1] - lines[-1][-1][1] < .6 * height:
            lines[-1].append(item)
        else:
            lines.append([item])
    # Blocks: a gap above 3 x height, or no horizontal overlap, starts a new block.
    blocks, current = [], [lines[0]]
    for previous, line in zip(lines, lines[1:]):
        gap = np.mean([i[1] for i in line]) - np.mean([i[1] for i in previous])
        lo = max(min(i[3].min() for i in previous), min(i[3].min() for i in line))
        hi = min(max(i[3].max() for i in previous), max(i[3].max() for i in line))
        if gap > 3 * height or hi - lo < -.5 * height:
            blocks.append(current)
            current = [line]
        else:
            current.append(line)
    blocks.append(current)
    def weight(block):
        return sum(i[0].get('score', 0) * len(i[0].get('key', '')) for line in block for i in line
                   if any(c.isdigit() for c in i[0].get('key', '')) and not i[0].get('exclusion_reason'))
    main = max(blocks, key=weight)
    block_height = float(np.median([i[2] for line in main for i in line])) or height
    for index, line in enumerate(main):
        for row, _, h, _ in line:
            row['block_line'] = index
            row['block_lines'] = len(main)
            row['block_height_ratio'] = h / block_height
    return dict(lines=len(main), blocks=len(blocks), direction=[float(u[0]), float(u[1])])


# --------------------------------------------------------------------- step 2
def _coded(row):
    key = row.get('key', '')
    return (any(c.isdigit() for c in key) and not row.get('exclusion_reason') and
            row.get('score', 0) >= .6 and len(key) >= 3)


def _logo(row, brand_words):
    key = row.get('key', '')
    return key.isalpha() or key in brand_words


def line_context(rows):
    """Per-line roles within the main block: first coded line, below a logo."""
    brand_words = brands()
    by_line = {}
    for row in rows:
        if row.get('block_line') is not None:
            by_line.setdefault(row['block_line'], []).append(row)
    coded_lines = sorted(i for i, members in by_line.items() if any(_coded(r) for r in members))
    logo_lines = {i for i, members in by_line.items()
                  if members and all(_logo(r, brand_words) for r in members if r.get('score', 0) >= .6)}
    brand_present = any(r.get('key', '') in brand_words for r in rows if r.get('score', 0) >= .7)
    for row in rows:
        line = row.get('block_line')
        row['coded_line_rank'] = coded_lines.index(line) if line in coded_lines else None
        row['below_logo'] = bool(line is not None and line - 1 in logo_lines)
        row['brand_present'] = brand_present
    return dict(coded_lines=len(coded_lines), logo_lines=sorted(logo_lines), brand=brand_present)


FEATURES = (
    'first_coded_line', 'second_coded_line', 'later_coded_line', 'not_in_block', 'below_logo',
    'large_print', 'small_print', 'single_line_block',
    'part_shape', 'stem_suffix', 'family_pattern', 'lot_shape', 'date_prefix', 'numeric_only',
    'short_text', 'long_text', 'one_letter_code',
    'db_exact', 'db_base', 'db_suggestion', 'db_correction',
    'ocr_score', 'multi_treatment', 'body_or_block_number',
    'rule_choice', 'rule_eligible',
)


# Starting weights from marking conventions (not fitted). Fitting starts here and
# is regularised towards these, so small datasets adjust rather than replace them.
PRIOR = dict(
    rule_choice=1.5, rule_eligible=.3, first_coded_line=.8, second_coded_line=.1,
    later_coded_line=-.3, not_in_block=-1., below_logo=.3, large_print=.2, small_print=-.2,
    part_shape=.5, stem_suffix=.3, family_pattern=.5, lot_shape=-.8, date_prefix=-.8,
    numeric_only=-.3, short_text=-.2, one_letter_code=-.5, db_exact=1., db_base=1.,
    db_suggestion=.2, db_correction=.3, ocr_score=1., multi_treatment=.2,
    body_or_block_number=.2, single_line_block=-.2, long_text=0.,
)


def line_features(row):
    from marking_context import DATE_CODE_PREFIX, longest_digit_run
    key = row.get('key', '')
    rank = row.get('coded_line_rank')
    letters = re.findall(r'[A-Z]+', key)
    trusted = row.get('trusted_database_matches') or []
    ratio = row.get('block_height_ratio') or 1.
    f = dict(
        first_coded_line=float(rank == 0),
        second_coded_line=float(rank == 1),
        later_coded_line=float(rank is not None and rank >= 2),
        not_in_block=float(row.get('block_line') is None),
        below_logo=float(bool(row.get('below_logo'))),
        large_print=float(ratio >= 1.15),
        small_print=float(ratio <= .85),
        single_line_block=float(row.get('block_lines', 0) <= 1),
        part_shape=float(bool(re.match(r'[A-Z]{2}', key)) and longest_digit_run(key) >= 3),
        stem_suffix=float(bool(re.fullmatch(r'[0-9]{4,8}[A-Z]{1,3}', key))),
        family_pattern=float(bool(row.get('part_pattern')) or
                             (row.get('kind') == 'family' and not row.get('weak_family_hint'))),
        lot_shape=float(len(re.findall(r'[0-9]+', key)) >= 2 and longest_digit_run(key) == 1),
        date_prefix=float(bool(DATE_CODE_PREFIX.match(key))),
        numeric_only=float(key.isdigit()),
        short_text=float(len(key) <= 4),
        long_text=float(len(key) >= 9),
        one_letter_code=float(len(letters) >= 1 and all(len(g) == 1 for g in letters) and
                              any(c.isdigit() for c in key)),
        db_exact=float(any(m.get('match_type') in ('exact', 'verified_alias') for m in trusted)),
        db_base=float(bool(trusted)),
        db_suggestion=float(bool(row.get('database_matches')) and not trusted or
                            bool(row.get('database_family_evidence'))),
        db_correction=float(bool(row.get('ocr_correction'))),
        ocr_score=float(row.get('score', 0)),
        multi_treatment=float(min(row.get('support', 1), 3) > 1),
        body_or_block_number=float(bool(row.get('ic_numeric'))),
    )
    return f


# --------------------------------------------------------------------- step 3
def logit(features, model):
    w = model.get('weights', {})
    return model.get('bias', 0.) + sum(w.get(name, 0.) * value for name, value in features.items())


def extended_pool(annotated):
    """Text from the main marking block that 0.8.3.2 never offered.

    The same hard filters as component_catalog.live_candidates apply, plus:
    a multi-line block, a digit, three or more characters and OCR >= 0.85.
    """
    pool = []
    # Same vetoes as live_candidates: database evidence pending (exact, base or
    # printed-family hit somewhere in the block) admits only rows that carry it.
    pending_identity = any((r.get('trusted_database_matches') or r.get('database_family_evidence')) and
                           r.get('box') and not r.get('exclusion_reason') and
                           r.get('score', 0) >= tuning('component_catalog.pending_database_score')
                           for r in annotated)
    for row in annotated:
        key = row.get('key', '')
        if (row.get('selection_block_reason') or
                (pending_identity and not row.get('trusted_database_matches') and
                 not row.get('database_family_evidence'))):
            continue
        if (row.get('exclusion_reason') or not row.get('box') or
                (row.get('conflicts') and not row.get('database_identity_consistent')) or
                (row.get('orientation_alternative') and not row.get('trusted_database_matches') and
                 not row.get('orientation_pattern_supported')) or
                row.get('block_line') is None or row.get('block_lines', 0) < 2 or
                len(key) < 3 or not any(c.isdigit() for c in key) or
                row.get('score', 0) < EXTENDED_MIN_SCORE):
            continue
        pool.append(row)
    return pool


def protected_choice(pool):
    """The rules' choice when it is a strong part-like marking or family
    pattern: a bare number (date/lot code with at most a database suggestion)
    never outranks it (0.8.3.4; e.g. 1841 vs NTP7515D)."""
    from marking_context import strong_marking
    for row in pool:
        if row['line_features'].get('rule_choice'):
            if strong_marking(row) or row['line_features'].get('family_pattern'):
                return row
            return None
    return None


def _guarded(row):
    f = row['line_features']
    return bool(f.get('numeric_only') and not f.get('db_base'))


def rank(annotated, legacy):
    """Order selectable rows by fitted score; returns (candidates, summary).

    legacy: the 0.8.3.2 selectable rows (already safety-filtered). Database-
    supported rows keep absolute priority, as before. Rows whose score is below
    the fitted abstain threshold are not auto-selected (they stay listed).
    """
    from ocr_core import candidate_id
    model = weights()
    block = marking_block(annotated)
    context = line_context(annotated)
    if any(r.get('trusted_database_matches') for r in legacy):
        pool = list(legacy)               # database evidence takes priority
    else:
        seen = {candidate_id(r) for r in legacy}
        pool = list(legacy) + [r for r in extended_pool(annotated) if candidate_id(r) not in seen]
    legacy_ids = [candidate_id(r) for r in legacy]
    for row in annotated:
        row['line_features'] = line_features(row)
        # The 0.8.3.2 rule order is evidence too: the model learns when block
        # position and text shape justify overriding it.
        row['line_features']['rule_choice'] = float(bool(legacy_ids) and candidate_id(row) == legacy_ids[0])
        row['line_features']['rule_eligible'] = float(candidate_id(row) in legacy_ids)
        row['line_score'] = logit(row['line_features'], model)
    pool.sort(key=lambda r: (bool(r['line_features']['db_exact']), bool(r['line_features']['db_base']),
                             r['line_score'], r.get('score', 0)), reverse=True)
    guard = protected_choice(pool)
    if guard is not None and pool and guard is not pool[0] and _guarded(pool[0]):
        pool.remove(guard)
        pool.insert(0, guard)
    # The abstain threshold only guards picks beyond the 0.8.3.2 rules: a rule
    # choice is never withheld, a new choice needs a convincing score.
    threshold = model.get('abstain_below')
    abstained = None
    if (pool and threshold is not None and not pool[0].get('trusted_database_matches') and
            not pool[0]['line_features']['rule_choice'] and pool[0]['line_score'] < threshold):
        abstained = pool[0].get('key')
        pool = []
    for row in annotated:
        terms = sorted(((name, model.get('weights', {}).get(name, 0.) * value)
                        for name, value in row['line_features'].items() if value), key=lambda t: -abs(t[1]))
        row['line_reason'] = ', '.join(f'{name} {value:+.2f}' for name, value in terms[:4] if abs(value) >= .05)
    summary = dict(version=VERSION, weights_version=model.get('version', 'none'),
                   fitted_on=model.get('fitted_on', ''), block=block, context=context,
                   pool=[dict(key=r['key'], score=round(r['line_score'], 3)) for r in pool[:8]],
                   abstained=abstained)
    return pool, summary
