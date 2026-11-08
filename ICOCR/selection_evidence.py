"""Within-image evidence; repeated transforms are not independent votes."""

from config_loader import tuning



def views(row):
    """Retain physical geometry from every observation, not only the winner."""
    return [row] if row.get('joined_from') else row.get('observation_evidence') or [row]


def compatible_views(a, b):
    # New observations carry pass IDs. Legacy replay can only check geometry.
    return (not a.get('pass_id') or not b.get('pass_id') or
            a['pass_id'] == b['pass_id'])


def weak_conflict(winner, other, winner_views, other_views):
    """Only dismiss clearly weaker readings; comparable readings still veto.

    Peak challenger confidence protects credible earlier evidence even if a
    later treatment weakens it. Scores are compared within one recognizer.
    No database identity or character substitution is inferred here.
    """
    best = max(r['score'] for r in winner_views)
    challenger = max(r['score'] for r in other_views)
    from marking_rules import part_pattern
    has_syntax = bool(part_pattern(winner))
    preferred = any(not r.get('orientation_alternative') and r['score'] >= tuning('selection_evidence.preferred_score')
                    for r in winner_views)
    strongest = max(winner_views, key=lambda r: r['score'])
    reverse_only = all(r.get('orientation_alternative') or
                       (r.get('rotation', 0) - strongest.get('rotation', 0)) % 360 == 180
                       for r in other_views)
    if (reverse_only and best >= tuning('selection_evidence.preferred_score') and challenger < tuning('selection_evidence.challenger_max_score') and best - challenger >= tuning('selection_evidence.conflict_score_gap') and
            preferred and has_syntax):
        return 'Weaker competing reading; strong preferred reading with bounded part syntax'
    return ''
