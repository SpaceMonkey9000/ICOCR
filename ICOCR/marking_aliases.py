"""Bounded, non-chaining family rules; raw OCR is immutable."""
import re
from config_loader import get_config
RULES = get_config('rules/marking_aliases.json')


# 0.8.9.6: ordering-code suffix after a hyphen (Microchip PIC18F252-I/SO,
# MCP2551-I/SN, ATMEGA328P-PU). OCR often turns "-I/SO" + "e3" into "-1S0E3".
ORDERING_SUFFIX = re.compile(r'[A-Z0-9/]{1,10}(?:-[A-Z0-9/]{1,10})?')


def ordering_suffix_matches(catalog, text):
    from config_loader import rule_enabled
    records_by_name = getattr(catalog, 'records', None)
    if not rule_enabled('match.ordering_suffix') or not records_by_name:
        return []
    key = text.strip().upper()
    if len(key) > 40 or '-' not in key:
        return []
    # Longest printed base first; the base must be an exact database name.
    cuts = [i for i, c in enumerate(key) if c == '-']
    for cut in reversed(cuts):
        base, suffix = key[:cut], key[cut+1:]
        if (len(base) < 5 or not re.search(r'[A-Z]', base) or not re.search(r'[0-9]', base) or
                not ORDERING_SUFFIX.fullmatch(suffix) or base not in records_by_name):
            continue
        # Hyphenated database variants (TCAN1042-Q1, BTA16-600B) are distinct parts: do not guess.
        if any(name.startswith(base + '-') for name in records_by_name):
            return []
        records = list(records_by_name[base])
        descriptions = {' '.join(str(r.get('entry_function') or r.get('component_function') or '').split()).casefold()
                        for r in records}
        descriptions.discard('')
        if len(descriptions) > 1:
            return []
        trace = dict(rule_id='match.ordering_suffix', observed=text, resolved_base=base,
                     operation='strip_ordering_suffix', suffix=suffix, inferred=True, label='ordering suffix')
        return [dict(r, manufacturer=r.get('manufacturer', ''), package='', qualifiers='', match_type='family_suffix',
                     identity_evidence='ordering suffix', applied_rule=trace, resolved_base=base) for r in records]
    return []


def matches(catalog, text):
    ordered = ordering_suffix_matches(catalog, text)
    if ordered:
        return ordered
    if not RULES['enabled']:
        return []
    key = text.strip().upper()
    parsed = re.fullmatch(r'(74)?([A-Z]{2,4})([0-9]{2,4})([A-Z]{0,3})', key)
    if not parsed:
        return []
    prefix, family, number, suffix = parsed.groups()
    if family not in RULES['families'] or (suffix and suffix not in RULES['suffixes']):
        return []
    if not prefix and (not RULES['abbreviations'] or suffix):
        return []  # no chained abbreviation + suffix inference
    if prefix and not suffix:
        return []
    target = '74' + family + number
    records = [r for r in catalog.find(target) if r.get('match_type') == 'exact' and r['part'].upper() == target]
    # Contradictory database descriptions cannot establish an unambiguous base.
    descriptions = {' '.join(str(r.get('entry_function') or r.get('component_function') or '').split()).casefold() for r in records}
    descriptions.discard('')
    if not records or len(descriptions) > 1:
        return []
    rule_id = ('74.abbreviation.' if not prefix else '74.package_suffix.') + family
    label = 'abbreviated marking' if not prefix else 'package suffix'
    trace = dict(rule_id=rule_id, observed=text, resolved_base=target,
                 operation='add_74_prefix' if not prefix else 'strip_explicit_suffix',
                 suffix=suffix, inferred=True, label=label)
    return [dict(r, manufacturer='', package='', qualifiers='', match_type='abbreviated' if not prefix else 'family_suffix',
                 identity_evidence=label, applied_rule=trace, resolved_base=target) for r in records]
