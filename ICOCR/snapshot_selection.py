"""Rank independent preprocessing attempts without manufacturing OCR votes.

Scores and support remain those of one attempt. Database identity is distinct
from recognition quality; same-tier small score differences retain the incumbent.
"""

from config_loader import tuning
VERSION = '1.0.0'


def quality(decision):
    row = decision.get('selected') or {}
    if not row or row.get('provisional') or (row.get('conflicts') and
                                            not row.get('database_identity_consistent')):
        return (0, 0.)
    matches = row.get('trusted_database_matches', [])
    tier = (6 if any(m.get('match_type') == 'exact' for m in matches) else
            5 if row.get('selected_database_match') else
            4 if row.get('part_pattern') else
            3 if row.get('kind') == 'family' and not row.get('weak_family_hint') else
            2 if row.get('context_marking') or row.get('ic_numeric') else 1)
    return tier, row.get('score', 0.)


def replacement_reason(incumbent, challenger):
    old, new = quality(incumbent), quality(challenger)
    # A later speculative marking must not displace an abstention or a better
    # transcription solely because one pass happened to make it selectable.
    if new[0] < 5 and new[1] < tuning('snapshot_selection.replacement_min_score'):
        return ''
    if new[0] > old[0]:
        return 'stronger selection evidence'
    if new[0] and new[0] == old[0] and new[1] > old[1] + tuning('snapshot_selection.replacement_score_margin'):
        return 'same evidence tier; OCR score improves by more than 0.05'
    return ''


def stop_reason(decision):
    tier, score = quality(decision)
    if tier >= 5:
        return 'database_supported_selection'
    if tier == 4 and score >= tuning('snapshot_selection.structured_stop_score'):
        return 'strong_structured_marking_identity_unresolved'
    return ''


def stage(decision, raw):
    row = decision.get('selected') or {}
    if row.get('selected_database_match'):
        return 'identity_resolved'
    if row:
        return 'marking_selected_identity_unresolved'
    return 'selection_unresolved' if raw else 'no_text_recognized'
