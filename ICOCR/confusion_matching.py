"""Database-guided correction of confused OCR characters (0.8.3.5).

Raw OCR is never rewritten: a correction is a database match of type
'corrected' that records every substitution. Costs are ranking heuristics, not
learned probabilities. There are no insertions or deletions, and missing text is
never completed (MCS6F does not become MC56F8006).

A correction is automatic (correction_eligible) only when:
  * exactly one database part is reachable from the reading,
  * at most 1 substitution for readings under 6 characters, 2 for 6-8 and 3 for
    9 or more, each a known confusion pair, with a bounded total cost,
  * the reading and the part both mix letters and digits (5+ characters),
  * a 0<->D swap inside the part name only counts when the corrected text is
    the whole name (a corrected package suffix may become a letter suffix).
The OCR-score and reading-direction gates are applied in component_catalog.
"""
import re

from config_loader import get_config
_CONFUSIONS = get_config('rules/ocr_confusions.json')
PAIRS = [(row['chars'][0], row['chars'][1], row['cost']) for row in _CONFUSIONS['pairs']]


def _fold_classes(pairs):
    # Connected components only accelerate lookup. _edits still requires each
    # individual substitution to be explicitly listed in PAIRS.
    groups = []
    for a, b, _ in pairs:
        joined = {a, b}
        matches = [g for g in groups if g & joined]
        for group in matches:
            joined.update(group)
            groups.remove(group)
        groups.append(joined)
    return [''.join(sorted(group)) for group in groups]


CLASSES = _fold_classes(PAIRS)
FOLD = {c: group[0] for group in CLASSES for c in group}
COST = {}
for a, b, cost in PAIRS:
    COST[a, b] = COST[b, a] = cost
SWAPS = {}                              # kept for callers of the 0.8.3 module
for a, b, cost in PAIRS:
    SWAPS.setdefault(a, []).append((b, cost))
    SWAPS.setdefault(b, []).append((a, cost))
# A digit misread in a package suffix: the letter it most often stands for.
SUFFIX_LETTER = _CONFUSIONS['suffix_letters']
MAX_SUFFIX = _CONFUSIONS['max_suffix']
_CONTEXT_COSTS = tuple((re.compile(row['prefix_pattern']), row['to_char'], row['cost'], row['id'])
                      for row in get_config('rules/device_families.json')['contextual_costs'] if row['enabled'])


def fold(text):
    return ''.join(FOLD.get(c, c) for c in text)


def max_edits(length):
    return next((row['max_edits'] for row in _CONFUSIONS['edit_limits'] if length <= row['max_length']),
                _CONFUSIONS['edit_limits'][-1]['max_edits'])


def max_cost(edits):
    return _CONFUSIONS['base_max_cost'] + _CONFUSIONS['extra_edit_cost'] * max(0, edits - 1)


def _mixed(text):
    return any(c.isalpha() for c in text) and any(c.isdigit() for c in text)


def fold_index(records, owner=None):
    """fold(name) -> names, cached on the owner (normally the Catalog) and
    invalidated when its records dict is replaced or resized. Without an owner
    the index is rebuilt (small test catalogues / direct callers)."""
    cached = getattr(owner, '_fold_index_cache', None) if owner is not None else None
    if cached and cached[0] is records and cached[1] == len(records):
        return cached[2]
    index = {}
    for name in records:
        index.setdefault(fold(name), []).append(name)
    if owner is not None:
        try:
            owner._fold_index_cache = (records, len(records), index)
        except AttributeError:
            pass
    return index


def _edits(observed, target):
    """Substitutions turning observed into target, or None if any pair is not
    a listed confusion (same fold class is necessary, not sufficient: D/Q, L/T)."""
    edits = []
    for i, (a, b) in enumerate(zip(observed, target)):
        if a != b:
            if (a, b) not in COST:
                return None
            edits.append(dict(index=i, from_char=a, to_char=b, cost=COST[a, b], rule_id='ocr.confusion.'+''.join(sorted((a,b)))))
    return edits


def candidates(text, records, owner=None):
    """Every database name reachable by confusion substitutions (any count)."""
    key = text.strip().upper()
    if key in records or not re.fullmatch(r'[A-Z0-9-]{4,24}', key) or not _mixed(key):
        return []
    index = fold_index(records, owner)
    found = []
    for n in range(0, MAX_SUFFIX + 1):
        base, suffix = (key[:-n], key[-n:]) if n else (key, '')
        if len(base) < 4:
            break
        # A stripped suffix must read as letters, after fixing digit misreads.
        suffix_edits = []
        if n:
            fixed = ''
            for j, c in enumerate(suffix):
                if c.isalpha():
                    fixed += c
                elif c in SUFFIX_LETTER:
                    fixed += SUFFIX_LETTER[c]
                    suffix_edits.append(dict(index=len(base) + j, from_char=c, to_char=SUFFIX_LETTER[c],
                                             cost=COST[c, SUFFIX_LETTER[c]]))
                else:
                    fixed = None
                    break
            if fixed is None:
                continue
        else:
            fixed = ''
        for name in index.get(fold(base), ()):
            if name == key or len(name) != len(base):
                continue
            edits = _edits(base, name)
            if edits is None:
                continue
            edits += suffix_edits
            if not edits:
                continue
            # Context changes cost only for an already-listed substitution.
            for e in edits:
                for prefix, target, cost, rule_id in _CONTEXT_COSTS:
                    if (e['to_char'] == target and prefix.fullmatch(name[:e['index']]) and
                            e['index'] < len(name)):
                        e['cost'] = cost
                        e['contextual_rule_id'] = rule_id
                        break  # First matching rule wins.
            found.append(dict(part=name, corrected_text=name + fixed, observed=key, edits=edits,
                              suffix=fixed, index=edits[0]['index'], from_char=edits[0]['from_char'],
                              to_char=edits[0]['to_char'], cost=round(sum(e['cost'] for e in edits), 3)))
    return sorted(found, key=lambda r: (len(r['edits']), r['cost'], r['part']))


def eligible(choice, unique):
    edits = choice['edits']
    observed = choice['observed']
    if not unique or len(observed) < 5 or len(choice['part']) < 5 or not _mixed(choice['part']):
        return False
    if len(edits) > max_edits(len(observed)) or choice['cost'] > max_cost(len(edits)) + 1e-9:
        return False
    base_len = len(choice['part'])
    if any({e['from_char'], e['to_char']} == {'0', 'D'} and e['index'] < base_len for e in edits) \
            and choice['corrected_text'] != choice['part']:
        return False
    return True


def matches(catalog, text):
    """All suggestions; automatic eligibility requires a single reachable part."""
    choices = candidates(text, catalog.records, catalog)
    unique = len({c['part'] for c in choices}) == 1
    result = []
    for choice in choices:
        ok = eligible(choice, unique)
        result.extend(dict(record, match_type='corrected', correction=dict(choice),
                           correction_eligible=ok) for record in catalog.records[choice['part']])
    return result
