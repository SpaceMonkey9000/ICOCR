"""Bounded part-number syntax hints. These never establish device identity.

Only whitespace at specified boundaries may be joined. Numeric suffixes on a
separate token are deliberately excluded: they are often dates or lot numbers.
"""
from functools import lru_cache
import re

from config_loader import get_config

_FAMILIES = get_config('rules/device_families.json')
_NEGATIVE = get_config('rules/negative_words.json')
ORIENTATION_PATTERN_MIN_SCORE = _FAMILIES['orientation_min_score']
ORIENTATION_PATTERN_MAX_SCORE_GAP = _FAMILIES['orientation_max_score_gap']
_RULES = tuple((row['label'], row['pattern']) for row in _FAMILIES['strict_patterns'] if row['enabled'])
PATTERNS = tuple((label, re.compile(pattern)) for label, pattern in _RULES)
HINT_PATTERNS = tuple((row['label'], re.compile(row['pattern']))
                      for row in _FAMILIES['hint_patterns'] if row['enabled'])


def part_pattern(text):
    key = text.strip().upper()
    known = next((label for label, pattern in PATTERNS if pattern.fullmatch(key)), '')
    if known:
        return known
    from prefix_rules import marking_rule
    row, _ = marking_rule(key)
    return row['name'] if row else ''


# Whole-line grammars, not free concatenation. No joining logos, lot/date text,
# two independent parts or different OCR boxes. Preserve the original elsewhere.
_SPACED = tuple(re.compile(row['pattern']) for row in _FAMILIES['spaced_patterns'] if row['enabled'])


def joined_line_marking(text):
    line = text.strip().upper()
    if not re.search(r'\s', line) or not any(p.fullmatch(line) for p in _SPACED):
        return ''
    compact = re.sub(r'\s+', '', line)
    return compact if part_pattern(compact) else ''


# Exact metadata words only. Do not use substring/fuzzy matching: short top
# marks and mixed identifiers must remain available as device candidates.
ORIGIN_WORDS = frozenset(_NEGATIVE['origin_words'])
ORIGIN_PHRASES = frozenset(_NEGATIVE['origin_phrases'])
EXTRA_EXACT = frozenset(_NEGATIVE['extra_exact'])


_PHRASE_COUNTRY = frozenset(phrase + ' ' + country for phrase in ORIGIN_PHRASES for country in ORIGIN_WORDS)
_TOKENS = re.compile(r'[A-Z0-9]+')


@lru_cache(maxsize=4096)
def origin_exclusion(text):
    words = ' '.join(_TOKENS.findall(text.upper()))
    if words in EXTRA_EXACT:
        return 'Excluded metadata text — not a device marking'
    if words in ORIGIN_WORDS or words in ORIGIN_PHRASES or words in _PHRASE_COUNTRY:
        return 'Country/origin text — not a device marking'
    return ''
