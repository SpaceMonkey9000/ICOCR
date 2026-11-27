"""Scan-local observational logging; never used for recognition decisions."""
from contextvars import ContextVar
from time import perf_counter
from version import VERSION

_active = ContextVar('recognition_trace', default=None)


def begin():
    events = []
    return _active.set((perf_counter(), events)), events


def end(token):
    _active.reset(token)


def active():
    return _active.get() is not None


def event(stage, **data):
    active = _active.get()
    if active is not None:
        started, events = active
        events.append(dict(ms=round((perf_counter()-started)*1000, 2), stage=stage, **data))


def matches(rows):
    return [{k: m[k] for k in ('part', 'manufacturer', 'match_type', 'alias_packages',
                              'package', 'identity_evidence', 'correction_eligible', 'correction') if k in m}
            for m in rows or []]


def candidate(row):
    fields = ('key','text','raw_text','score','rank','display_rank','selection_rank','line_score',
              'line_reason','kind','box','rotation','retention_eligible','selection_tier',
              'selection_decision','selection_reason','rejection_reason','exclusion_reason',
              'conflicts','alias_ambiguous','database_ambiguous','corrected_alias_issue',
              'orientation_alternative','selection_block_reason','observed_markings','support','modes','evidence','conflict_evidence')
    out = {k: row[k] for k in fields if k in row}
    out['lookup_key'] = str(row.get('text', row.get('key', ''))).strip().upper()
    out['database_matches'] = matches(row.get('database_matches'))
    out['trusted_matches'] = matches(row.get('trusted_database_matches'))
    out['correction_suggestions'] = matches(row.get('correction_suggestions'))
    out['corrected_alias_suggestions'] = matches(row.get('corrected_alias_suggestions'))
    out['selected_match'] = matches([row['selected_database_match']]) if row.get('selected_database_match') else []
    out['applied_rules'] = [r.get('rule_id') for r in row.get('applied_rules', [])]
    return out


def identity(row):
    match = row.get('selected_database_match') or {}
    return dict(marking=row.get('key'), ocr_confidence=row.get('score'),
                identification_status=('ambiguous' if row.get('database_ambiguous') else
                    'database-backed: '+str(match.get('match_type')) if match else 'unverified' if row else 'none'),
                part=match.get('part'), manufacturer=match.get('manufacturer'),
                selection_reason=row.get('selection_reason') or row.get('provisional_reason'))


def pipeline(decision, d):
    decision = decision or {}
    keys = ('scan_input','body_detection','body_model_error','body_model_detections',
            'model_body_outlines','package_classification','runtime','timings','treatments',
            'selected_rotation','deskew_degrees','ocr_calls','retry_calls','retry_reason',
            'retry_deferred','targeted_original','early_exit','live_budget_limited',
            'reverse_reads_skipped','straightened_fallback','live_prefix','note')
    out = {k:d[k] for k in keys if k in d}
    out['raw_ocr_readings'] = d.get('raw_observations', d.get('raw', []))
    out['normalised_observations'] = d.get('observations', [])
    out['outside_body_rejected'] = [candidate(r) for r in d.get('outside_body_candidates', [])]
    out['candidates'] = [candidate(r) for r in decision.get('all_candidates', [])]
    out['line_ranking'] = decision.get('line_ranking')
    out['identification'] = identity(decision.get('selected') or decision.get('provisional') or {})
    if 'body_recovery' in d:
        recovery = d['body_recovery']
        out['body_recovery'] = {k:v for k,v in recovery.items() if not k.endswith('_scan_result')}
    if 'preprocessing' in d:
        p = d['preprocessing']
        out['preprocessing'] = {k:p[k] for k in ('mode','stage','selected_preset','stop_reason') if k in p}
    return out


def report(decision, diagnostics, catalog=None):
    decision = decision or {}
    cfg = decision.get('configuration') or {}
    modules = cfg.get('modular_rules', {}).get('modules', [])
    result = dict(version=VERSION, summary=identity(decision.get('selected') or decision.get('provisional') or {}),
                  database=getattr(catalog, 'diagnostic_metadata', None) if catalog is not None else None,
                  settings=diagnostics.get('scan_settings', {}),
                  limitations=['Combined OCR mode exposes only engine-returned readings; internally rejected text regions are unavailable.', 'Identification status is evidence-based, not a calibrated probability.'],
                  enabled_rules=[m.get('name', m.get('id')) for m in modules if m.get('enabled')],
                  line_ranking_enabled=cfg.get('line_ranking_enabled'),
                  configuration_hash=cfg.get('effective_sha256'),
                  pipeline=pipeline(decision, diagnostics),
                  execution_trace=diagnostics.get('execution_trace', []))
    if 'chip_diagnostics' in diagnostics:
        result['chips'] = [dict(index=c['index'], status=c['status'], region=c['region'],
                                error=c.get('error'), pipeline=pipeline(c['diagnostics'].get('scan_result'), c['diagnostics']))
                           for c in diagnostics['chip_diagnostics']]
    return result
