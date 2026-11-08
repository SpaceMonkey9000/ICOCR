"""Explicit missing-prefix candidates; never promote an inferred SKU to identity."""
import re
from config_loader import RULES

ACTIVE = tuple((row, re.compile(row['pattern'])) for row in RULES.modules
               if row['kind'] == 'prefix_candidates' and row['enabled'])


def marking_rule(text):
    key = text.strip().upper()
    if len(key) > 32:
        return None, ''
    for row, pattern in ACTIVE:
        base = key[:-1] if row['ignore_trailing_hyphen'] and key.endswith('-') else key
        if pattern.fullmatch(base):
            return row, base
    from database_rules import marking_rule as additional_marking
    return additional_marking(key)


def matches(catalog, text):
    key = text.strip().upper()
    if len(key) > 32:
        return []
    result = []
    # Combine overlapping rules without selecting one inferred identity.
    for row, pattern in ACTIVE:
        base = key[:-1] if row['ignore_trailing_hyphen'] and key.endswith('-') else key
        if not pattern.fullmatch(base):
            continue
        # Exact generated names only: no fuzzy matching or chained affix removal.
        for prefix in row['prefixes']:
            for suffix in row['suffixes']:
                name = prefix + base + suffix
                for record in catalog.records.get(name, ()):
                    result.append(dict(record, match_type='rule_candidate', identity_evidence='missing prefix; unverified',
                        applied_rule=dict(rule_id=row['id'], observed=text, lookup_base=base,
                                          candidate=name, inferred=True)))
    from database_rules import matches as additional_matches
    result.extend(additional_matches(catalog, text))
    unique = []
    for record in result:
        if not any({k: v for k, v in record.items() if k not in ("applied_rule", "identity_evidence")} ==
                   {k: v for k, v in old.items() if k not in ("applied_rule", "identity_evidence")} for old in unique):
            unique.append(record)
    return unique
