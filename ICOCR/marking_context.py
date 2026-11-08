"""Geometric support for unfamiliar printed marks, never device identity."""
from config_loader import tuning, rule_enabled
import re
import numpy as np
from selection_evidence import views, compatible_views

# 0.8.3.1 selection rules (marking syntax only; never device identity).
# A date-code prefix: YYWW (years 00-27, week 01-53) followed by a letter,
# e.g. 2235D4, 1732A6. Raise the year bound as new date codes appear.
DATE_CODE_PREFIX = re.compile(r'^(?:[01][0-9]|2[0-7])(?:0[1-9]|[1-4][0-9]|5[0-3])[A-Z]')
LOT_CODE_PENALTY = tuning('marking_context.lot_rank_penalty')
SHORT_BLOCK_MIN_SCORE = tuning('marking_context.short_block_min_score')
SHORT_BLOCK_PENALTY = tuning('marking_context.short_block_rank_penalty')


def longest_digit_run(key):
    return max((len(run) for run in re.findall(r'[0-9]+', key)), default=0)


def short_block_marking(key):
    """Short top marks with one 2-3 letter group (VP251, HC32, 2QP17, AHC08).

    One-letter codes (B663, P185, J803P, 185X014) remain lot-shaped, as before.
    Block support (aligned neighbouring lines) is still required by the caller,
    and these rank below printed numeric identifiers (SHORT_BLOCK_PENALTY).
    """
    return bool(re.fullmatch(r'[0-9]{0,2}[A-Z]{2,3}[0-9]{2,5}', key) and
                not DATE_CODE_PREFIX.match(key))


def lot_code_penalty(row):
    """Rank penalty for unverified text that matches lot/date-code grammar."""
    if not rule_enabled('context.lot_penalty') or row.get('trusted_database_matches') or row.get('part_pattern'):
        return 0.
    key = row['key']
    runs = re.findall(r'[0-9]+', key)
    if not runs or not any(c.isalpha() for c in key):
        return 0.
    interleaved = len(runs) >= 2 and longest_digit_run(key) == 1
    return LOT_CODE_PENALTY if (interleaved or DATE_CODE_PREFIX.match(key)) else 0.


def _neighbours(row, rows, max_distance=3, min_ratio=tuning('marking_context.neighbour_height_min'), max_ratio=tuning('marking_context.neighbour_height_max')):
    """Distinct nearby parallel lines in the same physical reading direction.

    OCR rotation labels can differ for the same deskewed block; use box edges.
    Overlapping alternative spellings cannot supply block support.
    """
    if not row.get('box'):
        return []
    a = np.asarray(row['box'], dtype=float)
    if a.shape != (4, 2) or not np.isfinite(a).all():
        return []
    edge = a[1] - a[0]
    width = np.linalg.norm(edge)
    if width < 2:
        return []
    u = edge / width
    v = np.array([-u[1], u[0]])
    height = np.ptp(a @ v)
    if height < 2:
        return []
    result = []
    for other in rows:
        if (not compatible_views(row, other) or other is row or other['key'] == row['key'] or not other.get('box') or
                other.get('orientation_alternative') or other.get('score', 0) < tuning('marking_context.neighbour_min_score') or
                other.get('exclusion_reason') == 'PCB reference designator' or len(other['key']) < 3):
            continue
        b = np.asarray(other['box'], dtype=float)
        if b.shape != (4, 2) or not np.isfinite(b).all():
            continue
        direction = b[1] - b[0]
        length = np.linalg.norm(direction)
        if length < 2 or np.dot(u, direction / length) < tuning('marking_context.neighbour_alignment_cosine'):
            continue
        bh = np.ptp(b @ v)
        offset = abs(np.dot(b.mean(axis=0) - a.mean(axis=0), v))
        overlap = min((a @ u).max(), (b @ u).max()) - max((a @ u).min(), (b @ u).min())
        if (min_ratio <= bh / height <= max_ratio and tuning('marking_context.neighbour_offset_min') * height <= offset <= max_distance * height and
                overlap >= tuning('marking_context.neighbour_overlap_min') * min(np.ptp(a @ u), np.ptp(b @ u))):
            result.append(other)
    return result


def expand_views(rows):
    """Every retained observation view of every row (see selection_evidence.views)."""
    return [dict(other, **view) for other in rows for view in views(other)]


def neighbours(row, rows, expanded=None, **geometry):
    if expanded is None:
        expanded = expand_views(rows)
    found = []
    for view in views(row):
        if view.get('orientation_alternative') or view.get('score', 0) < tuning('marking_context.view_min_score'):
            continue
        found.extend(_neighbours(dict(row, **view), expanded, **geometry))
    from ocr_core import same_text_region
    unique = []
    for other in found:
        if not any(same_text_region(other['box'], old['box']) for old in unique):
            unique.append(other)
    return unique


def contextual_marking(row, rows, expanded=None):
    """Admit strong mixed marks, or short alphabetic codes with block support.

    Four-digit numbers still require the existing IC body/numeric-block rules.
    Body evidence alone leaves unfamiliar codes provisional as before.
    """
    key = row['key']
    if (not rule_enabled('context.block') or row.get('kind') != 'context' or row.get('exclusion_reason') or
            row.get('orientation_alternative') or row.get('conflicts') or
            row.get('score', 0) < tuning('marking_context.context_min_score') or not re.fullmatch(r'[A-Z0-9]{4,16}', key)):
        return ''
    # Numeric-led interleaved codes (e.g. digits/letters/digits) are common lot
    # codes. Admit only a substantial numeric stem plus alphabetic suffix, or
    # longer letter-led mixed marks. Short ambiguous mixed codes stay provisional.
    mixed = bool(re.fullmatch(r'\d{4,8}[A-Z]{1,3}', key) or
                 (len(key) >= 6 and key[0].isalpha() and any(c.isdigit() for c in key)))
    short_alpha = key.isalpha() and 4 <= len(key) <= 6 and row.get('score', 0) >= tuning('marking_context.alpha_min_score')
    # New in 0.8.3.1; a higher score is required than for longer markings.
    short_block = short_block_marking(key) and row.get('score', 0) >= SHORT_BLOCK_MIN_SCORE
    if not (mixed or short_alpha or short_block):
        return ''
    if expanded is None:
        expanded = expand_views(rows)
    nearby = neighbours(row, rows, expanded)
    # Alphabetic text may be a logo. Require two supporting number-bearing
    # lines, rather than one nearby code, before treating it as a top mark.
    if short_alpha:
        nearby = [r for r in nearby if any(c.isdigit() for c in r['key'])]
        if len({r['key'] for r in nearby}) < 2:
            return ''
        # A logo above a stack of codes is not strong top-mark evidence.
        # Require number-bearing lines on both sides of one retained view.
        surrounded = False
        for view in views(row):
            if not view.get('box') or view.get('score', 0) < tuning('marking_context.alpha_min_score'):
                continue
            a = np.asarray(view['box'], dtype=float)
            edge = a[1] - a[0]
            length = np.linalg.norm(edge)
            if length < 2:
                continue
            v = np.array([-edge[1], edge[0]]) / length
            offsets = [float((np.asarray(n['box']).mean(axis=0)-a.mean(axis=0)) @ v)
                       for n in _neighbours(dict(row, **view), expanded)
                       if any(c.isdigit() for c in n['key'])]
            if offsets and min(offsets) < 0 < max(offsets):
                surrounded = True
                break
        if not surrounded:
            return ''
    return 'nearby aligned marking lines' if nearby else ''


def context_rank_bonus(row):
    # Weak preference within unfamiliar block markings, not a family rule.
    # A longer letter-led mixed identifier outranks a similarly clear numeric-
    # led code. Lot/date-code grammar is ranked down. No text or database
    # identity is altered.
    key = row['key']
    bonus = tuning('marking_context.context_rank_bonus') if (rule_enabled('context.rank_bonus') and row.get('context_marking') and len(key) >= 6 and
                    key[0].isalpha() and any(c.isdigit() for c in key)) else 0.
    if rule_enabled('context.short_penalty') and row.get('context_marking') and short_block_marking(key) and not strong_marking(row):
        bonus -= SHORT_BLOCK_PENALTY
    return bonus - lot_code_penalty(row)


def strong_marking(row):
    """Letter-led, part-like unfamiliar text: two leading letters and a run of
    three or more digits (DA8950M, VP251, GAD311, RTL9000AN), or a 4-8 digit
    stem with a 1-3 letter suffix (2903M, 9013M, 9241H)."""
    key = row['key']
    part_like = ((re.match(r'[A-Z]{2}', key) and longest_digit_run(key) >= 3) or
                 re.fullmatch(r'[0-9]{4,8}[A-Z]{1,3}', key))
    return bool((row.get('kind') == 'unknown' or row.get('context_marking')) and
                part_like and not lot_code_penalty(row))


def selection_order(row):
    """Sort-key fragment for unfamiliar markings (0.8.3.1): (strong, rank).

    Part-like text (strong_marking) outranks other unverified text whether it
    came from syntax ('unknown') or block support (context marking). Below
    that, the existing evidence rank decides, as in 0.8.3.
    """
    return strong_marking(row), row.get('selection_rank', row.get('rank', 0))
