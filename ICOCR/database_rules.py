"""Bounded database-supported suggestions. No inferred identity or pinout changes."""
import re
from config_loader import RULES

ACTIVE = tuple(r for r in RULES.modules if r['kind'] == 'database_rule' and r['enabled'])
MOSFET = re.compile(r'([A-Z]+)([0-9]{1,3}[NP][0-9]{2,3})([A-Z][A-Z0-9]{0,11})?')
SHORT_MOSFET = re.compile(r'([0-9]{1,3}[NP][0-9]{2,3})([A-Z][A-Z0-9]{0,11})?')


def extra_prefixes():
    return [v for row in ACTIVE if row['recipe'] == 'prefix_hints' for v in row['values']]


def marking_rule(text):
    for row in ACTIVE:
        recipe = row['recipe']
        if recipe == 'prefix_hints' and any(re.fullmatch(re.escape(v)+r'[0-9][A-Z0-9/.-]*', text) for v in row['values']):
            return row, text
        if recipe == 'mosfet' and SHORT_MOSFET.fullmatch(text.removesuffix('-')):
            return row, text.removesuffix('-')
    return None, ''


def function_is(record, device):
    descriptions = [str(record.get(k) or '').casefold() for k in ('entry_function', 'component_function')]
    descriptions = [d for d in descriptions if d.strip()]
    if not descriptions:
        return False
    blocked = r'\b(driver|controller|igbt|regulator)\b'
    if any(re.search(blocked, d) for d in descriptions):
        return False
    required = r'\bmosfet\b' if device == 'mosfet' else r'\b(transistor|npn|pnp|jfet|mosfet)\b'
    return any(re.search(required, d) for d in descriptions)


def compact(name):
    # Decimal points and slashes have meaning and are deliberately retained.
    return name.replace('-', '').replace(' ', '')


def indexes(catalog):
    cached = getattr(catalog, '_database_rule_indexes', None)
    if cached is not None:
        return cached
    mosfets, separators = {}, {}
    for name, records in catalog.records.items():
        parsed = MOSFET.fullmatch(name)
        if parsed:
            _, stem, suffix = parsed.groups()
            valid = [r for r in records if function_is(r, 'mosfet')]
            if valid:
                mosfets.setdefault(stem, []).extend((r, suffix or '') for r in valid)
        if '-' in name or ' ' in name:
            separators.setdefault(compact(name), []).extend(records)
    cached = (mosfets, separators)
    catalog._database_rule_indexes = cached
    return cached


def matches(catalog, text):
    key = text.strip().upper()
    if not getattr(catalog, 'records', None) or not 4 <= len(key) <= 32 or key in catalog.records:
        return []
    result = []
    for row in ACTIVE:
        recipe, records = row['recipe'], []
        if recipe == 'transistor':
            parsed = re.fullmatch(r'([ABCDJK])([0-9]{3,5}[A-Z]{0,2})', key)
            if parsed and parsed[1] in row['values']:
                # Explicit alternatives remain separate identities.
                names = ['2S'+key]
                if parsed[1] in 'AC':
                    names.append('KS'+key)
                records = [r for n in names for r in catalog.records.get(n, ()) if function_is(r, 'transistor')]
        elif recipe == 'logic':
            parsed = re.fullmatch(r'([A-Z]{1,4})([0-9]{2,4})', key)
            if parsed and parsed[1] in row['values']:
                records = catalog.records.get('74'+key, ())
        elif recipe == 'mosfet':
            parsed = SHORT_MOSFET.fullmatch(key.removesuffix('-'))
            if parsed:
                stem, suffix = parsed.groups()
                records = [r for r, ending in indexes(catalog)[0].get(stem, ()) if not suffix or suffix == ending]
        elif recipe == 'separators' and len(key) >= 5 and re.fullmatch(r'[A-Z0-9. -]+', key):
            records = indexes(catalog)[1].get(compact(key), ())
        for record in records:
            result.append(dict(record, match_type='rule_candidate', identity_evidence='database-supported suggestion; unverified',
                applied_rule=dict(rule_id=row['id'], observed=text, lookup_base=key,
                                  candidate=record['part'], inferred=True)))
    return result
