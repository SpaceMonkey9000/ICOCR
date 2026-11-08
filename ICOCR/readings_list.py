"""Recognised-markings list: every usable reading stays visible (0.8.3.4).

The automatic selection is a convenience, not a gate. The technician can always
pick the correct (or closest) reading from the list:

  1. the automatic pick (or the provisional reading being checked),
  2. readings with database support,
  3. every other reading, best line score first (marking-block text before
     reverse readings and text outside the block),
  4. whole printed lines whose text differs from their tokens (e.g. "LM 2903M"),
  5. with Show all: excluded text (PCB references, origin text, short values).

If OCR produced no usable candidate at all, the raw OCR lines are listed.
"""
import re

MAX_ENTRIES = 30
MIN_SCORE = .50

AUTO, CHOSEN, DATABASE, CANDIDATE, OTHER, LINE, EXCLUDED, RAW = (
    'auto', 'chosen', 'database', 'candidate', 'other', 'line', 'excluded', 'raw')


def normalize(text):
    return re.sub(r'[^A-Z0-9-]', '', str(text).upper())


def _usable(row):
    key = row.get('key', '')
    return (len(key) >= 3 and row.get('score', 0) >= MIN_SCORE and
            (any(c.isdigit() for c in key) or len(key) >= 4))


def _rank(row):
    return (row.get('line_score') if row.get('line_score') is not None
            else row.get('selection_rank', row.get('rank', 0)), row.get('score', 0))


def _raw_rows(raw, mode='raw'):
    rows, seen = [], set()
    for reading in sorted(raw or [], key=lambda r: -float(r.get('score', 0))):
        text = ' '.join(str(reading.get('text', '')).split())
        key = normalize(text)
        if len(key) < 3 or key in seen or float(reading.get('score', 0)) < MIN_SCORE:
            continue
        seen.add(key)
        rows.append(dict(key=key, text=text, raw_text=text, score=float(reading.get('score', 0)),
                         rotation=reading.get('rotation', 0), box=reading.get('box'),
                         status='Raw OCR line — not evaluated', evidence='Raw OCR line',
                         database_matches=[], raw_line=True, list_source=mode))
    return rows


def build(scan_result, diagnostics=None, show_all=False, chosen=None):
    """Ordered list of (row, kind) for the Recognised markings list."""
    scan_result = scan_result or {}
    candidates = scan_result.get('all_candidates') or []
    entries, seen = [], set()
    def add(row, kind):
        key = row.get('key', '')
        if not key or key in seen or len(entries) >= MAX_ENTRIES:
            return
        seen.add(key)
        entries.append((row, kind))
    if chosen is not None:
        add(chosen, CHOSEN)
    automatic = scan_result.get('selected') or scan_result.get('provisional')
    if automatic:
        add(automatic, AUTO)
    usable = [r for r in candidates if _usable(r) and not r.get('exclusion_reason')]
    for row in sorted((r for r in usable if r.get('selected_database_match') or
                       r.get('trusted_database_matches')), key=_rank, reverse=True):
        add(row, DATABASE)
    block = [r for r in usable if r.get('block_line') is not None and not r.get('orientation_alternative')]
    # Identity, not equality: rows are dicts, and `r not in block` compared
    # whole dicts (O(n²) deep comparisons; equal-valued rows were confused).
    in_block = {id(r) for r in block}
    rest = [r for r in usable if id(r) not in in_block]
    for row in sorted(block, key=_rank, reverse=True):
        add(row, CANDIDATE)
    for row in sorted(rest, key=_rank, reverse=True):
        add(row, OTHER)
    if not entries:
        # Nothing evaluated as a candidate: offer the raw OCR lines themselves.
        for row in _raw_rows((diagnostics or {}).get('raw')):
            add(row, RAW)
    # Whole printed lines carry spacing and split codes the tokens lose.
    for row in _raw_rows((diagnostics or {}).get('raw'), LINE):
        if ' ' in row['text']:
            add(row, LINE)
    if show_all:
        for row in sorted((r for r in candidates if r.get('exclusion_reason')), key=_rank, reverse=True):
            add(row, EXCLUDED)
    return entries


def choice_status(row):
    return 'Clarified' if row.get('kind') == 'edited' else 'Selected'


def label(row, kind):
    """List text: marker, reading, and a short description."""
    marker = {AUTO: '★ ', CHOSEN: '✓ '}.get(kind, '   ')
    shown = (row['resolved_partnumber'] + ' [corrected from ' + row['key'] + ']'
             if row.get('ocr_correction') and row.get('resolved_partnumber') else
             row.get('text') if kind in (LINE, RAW) else row['key'])
    if (row.get('selected_database_match') or {}).get('match_type') == 'abbreviated' and row.get('resolved_partnumber'):
        shown = row['key'] + ' → ' + row['resolved_partnumber'] + ' [abbreviated marking]'
    if kind == CHOSEN:
        note = choice_status(row).lower()
    elif row.get('exclusion_reason'):
        note = row['exclusion_reason']
    elif row.get('function_summary'):
        note = row['function_summary']
    elif row.get('selected_database_match'):
        note = 'DB identity match'
    elif row.get('database_matches'):
        note = 'DB suggestions — identity unknown'
    elif kind == LINE:
        note = 'whole printed line'
    elif kind == RAW:
        note = 'raw OCR line'
    elif kind == AUTO and row.get('provisional'):
        note = 'checking — identity unknown'
    elif row.get('key', '').isdigit():
        note = 'numeric marking — identity unknown'
    elif kind == OTHER:
        note = 'outside the marking block / reverse reading'
    else:
        note = 'marking — identity unknown'
    if kind == AUTO and not row.get('provisional'):
        note = 'auto pick — ' + note
    return f'{marker}{shown} — {note}'


COLOURS = {AUTO: '#0b7a52', CHOSEN: '#1f5fbf', DATABASE: '#1b1b1b', CANDIDATE: '#1b1b1b',
           OTHER: '#666666', LINE: '#666666', EXCLUDED: '#999999', RAW: '#666666'}
