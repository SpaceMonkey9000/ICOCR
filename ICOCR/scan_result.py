"""One serializable selection decision shared by OCR, list, history and overlay."""
from config_loader import tuning
import re
import numpy as np
from component_catalog import annotate, live_candidates
from ocr_core import candidate_id
from marking_context import selection_order
import line_ranking
from config_loader import configuration_diagnostics


BLOCK_NUMERIC_SCORE = tuning('selection.block_numeric_score')
LOT_CODE_REASON = 'Lot/date code or label pattern — listed, not auto-selected'


def auto_selectable(row):
    """Part syntax, bounded block evidence or a trusted database match is needed.
    Unfamiliar marks remain unidentified; unsupported context stays unselected."""
    return bool(row.get('selected_database_match')) or (
        (row.get('kind') != 'context' or row.get('context_marking')) and
        (not row.get('orientation_alternative') or row.get('orientation_pattern_supported')))


def _line_geometry(box):
    points = np.asarray(box, dtype=float)
    direction = points[1] - points[0]
    length = float(np.linalg.norm(direction))
    if length < 1:
        return None
    u = direction / length
    v = np.array([-u[1], u[0]])
    return points.mean(axis=0), u, v, float(np.ptp(points @ v)), points @ u


def mark_block_numeric(rows):
    """Four digits require distinct nearby aligned text, not repeated crops."""
    from marking_context import neighbours, expand_views
    marked = []
    expanded = None   # geometry views only; unaffected by the flags set below
    for row in rows:
        if (row.get('ic_numeric') or not re.fullmatch(r'[0-9]{4}', row['key']) or
                row.get('score', 0) < BLOCK_NUMERIC_SCORE or row.get('conflicts')):
            continue
        if expanded is None:
            expanded = expand_views(rows)
        if neighbours(row, rows, expanded, max_distance=2, min_ratio=tuning('scan_result.numeric_neighbour_height_min'), max_ratio=tuning('scan_result.numeric_neighbour_height_max')):
            row['rank'] = row.get('rank', 0) - tuning('scan_result.numeric_rank_penalty')
            row.update(ic_numeric=True, ic_numeric_evidence='multi-line marking block',
                       kind='numeric', status='Numeric marking in a multi-line IC marking — identity unknown')
            marked.append(row)
    return marked


def build_scan_result(rows, all_rows, catalog=None, previous=None):
    all_rows = [dict(r) for r in all_rows]
    marked = mark_block_numeric(all_rows)
    annotated = annotate(all_rows, catalog)
    eligible = {candidate_id(r) for r in rows} | {candidate_id(r) for r in marked}
    eligible |= {candidate_id(r) for r in all_rows if r.get('ic_numeric')}
    eligible |= {candidate_id(r) for r in annotated if r.get('context_marking')}
    display = [r for r in annotated if candidate_id(r) in eligible or
               (r['database_matches'] and r.get('score', 0) >= tuning('scan_result.database_display_score'))]
    candidates = [r for r in live_candidates(annotated, catalog, annotated=True)
                  if (r.get('selected_database_match') or candidate_id(r) in eligible) and auto_selectable(r)]
    ranking = None
    if line_ranking.enabled():
        # 0.8.3.3: order by fitted line score (marking block position, text
        # shape, database and OCR evidence) instead of the fixed tier order.
        candidates, ranking = line_ranking.rank(annotated, candidates)
    incumbent_retained = False
    if previous and previous.get('score', 0) >= tuning('scan_result.incumbent_min_score') and candidates:
        from ocr_core import same_text_region
        incumbent = next((r for r in candidates if r['key'] == previous['key'] and
                          same_text_region(r.get('box'), previous.get('box'))), None)
        winner = candidates[0]
        def tier(r):
            return (any(m.get('match_type') in ('exact', 'verified_alias')
                        for m in r.get('trusted_database_matches', [])),
                    bool(r.get('trusted_database_matches')), bool(r.get('part_pattern')),
                    r.get('kind') == 'family' and not r.get('weak_family_hint'),
                    selection_order(r)[0])
        if (incumbent is not None and incumbent is not winner and
                tier(incumbent) == tier(winner) and
                winner['score'] - incumbent['score'] <= tuning('scan_result.incumbent_score_margin')):
            candidates.remove(incumbent)
            candidates.insert(0, incumbent)
            incumbent_retained = True
    accepted = {candidate_id(r) for r in candidates}
    has_database = any((r.get('trusted_database_matches') or r.get('database_family_evidence')) and r.get('box') and not r.get('exclusion_reason') and r.get('score',0)>=tuning('scan_result.pending_database_score') for r in annotated)
    for row in annotated:
        if candidate_id(row) in accepted:
            reason = ''
        elif row.get('exclusion_reason'):
            reason = row['exclusion_reason']
        elif ranking and ranking.get('abstained') == row['key']:
            reason = 'Line score below the automatic selection threshold'
        elif (row.get('orientation_alternative') and not row.get('selected_database_match') and
              not row.get('orientation_pattern_supported')):
            reason = 'Alternative reading direction — no database support'
        elif not auto_selectable(row):
            reason = LOT_CODE_REASON
        elif not row.get('box'):
            reason = 'Missing text position'
        elif row.get('conflicts') and not row['database_identity_consistent']:
            reason = 'Unresolved readings in the same text region'
        elif row.get('selection_block_reason'):
            reason = row['selection_block_reason']
        elif has_database and not row.get('selected_database_match'):
            reason = 'Exact/base database evidence takes priority over unmatched marking'
        else:
            reason = 'Below automatic selection confidence threshold'
        row['rejection_reason'] = reason
    # Preserve unresolved conflicts, strong unmatched readings blocked by a
    # weak database hit, and mixed short body markings for live verification.
    provisional = None
    if not candidates:
        def provisional_reason(r):
            if not r.get('box') or r.get('exclusion_reason') or r.get('score', 0) < tuning('scan_result.provisional_min_score'):
                return ''
            if (r.get('orientation_alternative') and not r.get('selected_database_match') and
                    not r.get('orientation_pattern_supported')):
                return ''
            if r.get('conflicts') and not r['database_identity_consistent'] and auto_selectable(r):
                return 'Conflicting readings — checking across frames'
            if r.get('score', 0) < tuning('scan_result.provisional_unmatched_score'):
                return ''
            if has_database and not r.get('selected_database_match') and auto_selectable(r):
                return 'Weak database evidence — checking unmatched marking'
            key = r['key']
            if (r.get('body_evidence') and r.get('kind') == 'context' and
                    re.fullmatch(r'[A-Z0-9-]{3,12}', key) and
                    any(c.isalpha() for c in key) and any(c.isdigit() for c in key)):
                return 'Marking on IC body — identity unknown'
            return ''
        pool = [r for r in annotated if provisional_reason(r)]
        if pool:
            provisional = dict(max(pool, key=lambda r: (r.get('rank', 0), r.get('score', 0))),
                               provisional=True)
            provisional['status'] = provisional_reason(provisional)
            provisional['provisional_reason'] = provisional['status']
    # Expose why an eligible row won or lost without mislabelling a ranking loss
    # as a confidence rejection. The diagnostic remains JSON-serializable.
    selected = candidates[0] if candidates else None
    for row in annotated:
        row['selection_decision'] = ('selected' if selected is row else
                                     'lower_priority' if candidate_id(row) in accepted else 'rejected')
        row['selection_reason'] = (row['rejection_reason'] if row['rejection_reason'] else
                                   'Eligible ' + row['selection_tier'] +
                                   ('; highest selection priority' if selected is row else
                                    '; another candidate ranks higher'))
        if row.get('ocr_correction'):
            row['selection_reason'] += '; one-character database correction from '+row['key']
        if row.get('orientation_pattern_supported'):
            row['selection_reason'] += '; part syntax supports alternative reading direction'
        if row.get('weak_family_hint'):
            row['selection_reason'] += '; broad W-prefix hint has reduced priority'
        if row.get('context_marking'):
            row['selection_reason'] += '; ' + row['context_marking']
        if ranking and row.get('line_reason'):
            row['selection_reason'] += f"; line score {row['line_score']:.2f} ({row['line_reason']})"
    if incumbent_retained:
        selected['selection_reason'] += '; prior eligible selection retained; no stronger replacement evidence'
    return dict(configuration=configuration_diagnostics(), incumbent_retained=incumbent_retained, line_ranking=ranking,
                all_candidates=annotated, display_candidates=display,
                candidates=candidates, selected=candidates[0] if candidates else None,
                provisional=provisional,
                selected_marking=selected['key'] if selected else '',
                observed_markings=selected.get('observed_markings', []) if selected else [],
                resolved_partnumber=selected.get('resolved_partnumber', '') if selected else '')
