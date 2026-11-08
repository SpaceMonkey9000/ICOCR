"""Read-only snapshot of the separate Component Database Builder catalogue."""
from config_loader import tuning, rule_enabled
from pathlib import Path
import logging
import re
import sqlite3
from collections import OrderedDict
from contextlib import closing
from functools import lru_cache
from threading import RLock
from marking_rules import (origin_exclusion, part_pattern, ORIENTATION_PATTERN_MIN_SCORE,
                           ORIENTATION_PATTERN_MAX_SCORE_GAP)
from marking_context import contextual_marking, context_rank_bonus, selection_order, expand_views

MAX_AFFIX_CHARS = tuning('matching.max_affix_chars')
CORRECTION_MIN_SCORE = tuning('selection.correction_min_score')   # OCR score needed for an automatic correction (0.90 before 0.8.3.5)
PCB_REFERENCE = re.compile(r'^(?:R|C|L|D|Q|U|IC|TP|LED|JP|J|CN|RN|RA|CA)[ -]*[0-9]{1,5}$')


# 0.8.9.4: resistor marking grammar. Values are checked against the standard
# E-series, so part numbers such as 555, 2904 or 7805 are not mistaken for
# resistor codes (55, 290 and 780 are not E24/E96 values).
E24 = (10, 11, 12, 13, 15, 16, 18, 20, 22, 24, 27, 30, 33, 36, 39, 43, 47, 51, 56, 62, 68, 75, 82, 91)
E96 = (100, 102, 105, 107, 110, 113, 115, 118, 121, 124, 127, 130, 133, 137, 140, 143, 147, 150, 154, 158,
       162, 165, 169, 174, 178, 182, 187, 191, 196, 200, 205, 210, 215, 221, 226, 232, 237, 243, 249, 255,
       261, 267, 274, 280, 287, 294, 301, 309, 316, 324, 332, 340, 348, 357, 365, 374, 383, 392, 402, 412,
       422, 432, 442, 453, 464, 475, 487, 499, 511, 523, 536, 549, 562, 576, 590, 604, 619, 634, 649, 665,
       681, 698, 715, 732, 750, 768, 787, 806, 825, 845, 866, 887, 909, 931, 953, 976)
_FOUR_DIGIT_BASES = frozenset(E96) | frozenset(10 * v for v in E24)   # 1 % parts also come in E24 values (4701)
_EIA96 = {'Z': .001, 'Y': .01, 'R': .01, 'X': .1, 'S': .1, 'A': 1, 'B': 10, 'H': 10, 'C': 100,
          'D': 1000, 'E': 10000, 'F': 100000}


def _ohms(value):
    for limit, unit in ((1e6, 'MΩ'), (1e3, 'kΩ')):
        if value >= limit:
            return f'{value/limit:g} {unit}'
    return f'{value:g} Ω'


def resistor_code(text, letters=True):
    """Resistance for a standard SMD resistor marking, else ''.

    Digits: 0/00/000/0000 jumpers, 3-digit E24 (472 = 4.7 kΩ), 4-digit E96 or
    1 % E24 (4701, 4991). Letters (optional): R-notation (4R7, 0R1, 49R9) and
    EIA-96 (01C = 10 kΩ). A bare R plus digits is a PCB reference, not handled here.
    """
    key = text.strip().upper()
    if re.fullmatch(r'0{1,4}', key):
        return '0 Ω jumper'
    m = re.fullmatch(r'([0-9]{2})([0-7])', key)
    if m and int(m[1]) in E24:
        return _ohms(int(m[1]) * 10 ** int(m[2]))
    m = re.fullmatch(r'([0-9]{3})([0-6])', key)
    if m and int(m[1]) in _FOUR_DIGIT_BASES:
        return _ohms(int(m[1]) * 10 ** int(m[2]))
    if not letters:
        return ''
    m = re.fullmatch(r'([0-9]{1,3})R([0-9]{0,3})', key)
    if m and len(key) <= 5:
        return _ohms(float(m[1] + '.' + (m[2] or '0')))
    m = re.fullmatch(r'([0-9]{2})([ZYRXSABHCDEF])', key)
    if m and 1 <= int(m[1]) <= 96:
        return _ohms(E96[int(m[1]) - 1] * _EIA96[m[2]])
    return ''


def _strict_family(text):
    from marking_rules import PATTERNS
    return any(pattern.fullmatch(text) for _, pattern in PATTERNS)


def automatic_exclusion(text):
    """Suppress board references and short numeric values in automatic IC ID.

    Short alphanumeric top marks are not rejected merely for being short.
    Exact explicit database lookup remains available for ambiguous short names.
    """
    origin = origin_exclusion(text)
    if origin:
        return origin
    text = text.strip().upper().strip('.:')
    if rule_enabled('exclude.numeric') and re.fullmatch(r'[0-9]{1,4}', text):
        value = resistor_code(text, letters=False)
        if value:
            return f'Resistor code {text} = {value}'
        # A strict device-family number (7805, 7912) is a part marking, not a value.
        if not _strict_family(text):
            return 'Short numeric marking / possible resistor value or date code'
    if rule_enabled('exclude.resistor_codes') and not text.isdigit():
        value = resistor_code(text)
        if value:
            return f'Resistor code {text} = {value}'
    if rule_enabled('exclude.repeated') and re.fullmatch(r'(.)\1{3,}', text):
        # 0.8.3.4: 2222222 on a non-IC image (ICBENCH test_image_104).
        return 'Repeated character — not a device marking'
    if rule_enabled('exclude.pcb_reference') and PCB_REFERENCE.fullmatch(text):
        return 'PCB reference designator'
    return ''


def bounded_part_match(left, right):
    """Literal containment with at most three extra characters on each side."""
    short, long = sorted((left, right), key=len)
    if not short:
        return False
    extra = len(long) - len(short)
    if extra > 2 * MAX_AFFIX_CHARS:
        return False
    # Check every permitted position: a later occurrence may satisfy both limits.
    return any(long.startswith(short, start)
               for start in range(max(0, extra - MAX_AFFIX_CHARS),
                                  min(MAX_AFFIX_CHARS, extra) + 1))


_INDEX_CACHE_VERSION = 2   # 2: JSON format (0.8.8); bump when the indexing rules or the catalogue query change


class Catalog:
    def __init__(self,path):
        self.path=Path(path).resolve();self.records={}
        # mode=ro ensures a typo cannot create or modify a database.
        with closing(sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True)) as db:
            db.execute('PRAGMA query_only=ON')
            ccols={r[1] for r in db.execute('PRAGMA table_info(components)')}
            ecols={r[1] for r in db.execute('PRAGMA table_info(entries)')}
            cf='c.function' if 'function' in ccols else "''"
            ef='e.function' if 'function' in ecols else "''"
            rows=db.execute(f'''SELECT c.part_number,c.manufacturer,c.family_hint,
                s.name,e.line,e.package_or_interface,e.qualifiers,{cf},{ef}
                FROM components c JOIN entries e ON e.component_id=c.id
                JOIN sources s ON s.id=e.source_id WHERE e.status='source_listed' ''')
            seen=set()
            for row in rows:
                if row in seen:continue
                seen.add(row)
                record=dict(zip(('part','manufacturer','family','source','line','package','qualifiers','component_function','entry_function'),row))
                self.records.setdefault(row[0].strip().upper(),[]).append(record)
        self.count=len(self.records)
        self._load_or_build_index()

    def _index_cache(self):
        """(cache file, validity key) for the on-disk alias index, or (None, None).

        0.8.8: the cache is JSON (data only). The previous pickle format could
        run code from a writable DATA folder; old ``.pickle`` files are never
        read and are removed when the new cache is written."""
        try:
            import hashlib
            import sys
            from project_paths import DATA
            stat = self.path.stat()
            wal = Path(str(self.path) + '-wal')
            wal = [wal.stat().st_size, wal.stat().st_mtime_ns] if wal.exists() else None
            key = [_INDEX_CACHE_VERSION, str(self.path), stat.st_size, stat.st_mtime_ns, wal,
                   MAX_AFFIX_CHARS, len(self.records), list(sys.version_info[:2])]
            name = hashlib.sha256(str(self.path).encode()).hexdigest()[:24] + '.json'
            return DATA / 'catalog_index' / name, key
        except OSError as exc:
            logging.warning('Catalogue index cache unavailable: %s', exc)
        except Exception:
            logging.exception('Catalogue index cache unavailable')
        return None, None

    @staticmethod
    def _valid_index(index):
        return (isinstance(index, dict) and
                all(isinstance(names, list) and all(isinstance(name, str) for name in names)
                    for names in index.values()))

    def _load_or_build_index(self):
        """Reuse the alias index saved for this exact database file (path, size,
        mtime); a missing, stale or unreadable cache falls back to building it
        in memory. Unexpected errors are logged, never raised."""
        import json
        cache, key = self._index_cache()
        if cache is not None:
            try:
                with open(cache, 'r', encoding='utf-8') as handle:
                    stored = json.load(handle)
                if (isinstance(stored, dict) and stored.get('key') == key and
                        self._valid_index(stored.get('index'))):
                    self.build_index(stored['index'])
                    return
            except FileNotFoundError:
                pass
            except (OSError, ValueError) as exc:   # unreadable or corrupt (JSONDecodeError is a ValueError)
                logging.warning('Ignoring catalogue index cache %s: %s', cache, exc)
            except Exception:
                logging.exception('Ignoring catalogue index cache %s', cache)
        self.build_index()
        if cache is not None:
            try:
                cache.parent.mkdir(parents=True, exist_ok=True)
                temporary = cache.with_suffix('.tmp')
                with open(temporary, 'w', encoding='utf-8') as handle:
                    json.dump(dict(key=key, index=self._affix_index), handle, separators=(',', ':'))
                temporary.replace(cache)
            except OSError as exc:
                logging.warning('Could not save catalogue index cache %s: %s', cache, exc)
            except Exception:
                logging.exception('Could not save catalogue index cache %s', cache)
            # Legacy pickle caches (<= 0.8.7) are never loaded; remove them.
            try:
                for legacy in cache.parent.glob('*.pickle'):
                    legacy.unlink()
            except OSError as exc:
                logging.warning('Could not remove legacy catalogue index cache: %s', exc)

    def build_index(self, index=None):
        """Index only legal affix removals; lookups never scan the catalogue."""
        if index is None:
            index = {}
            for name in self.records:
                aliases = {name[left:len(name)-right if right else None]
                           for left in range(MAX_AFFIX_CHARS+1)
                           for right in range(MAX_AFFIX_CHARS+1)
                           if left+right and left+right < len(name)}
                for alias in aliases:
                    index.setdefault(alias, []).append(name)
        self._affix_index = index
        self._indexed_records = self.records
        self._indexed_count = len(self.records)
        self._partial_cache = OrderedDict()
        self._cache_lock = RLock()

    def find(self,text,numeric_prefix=False):
        # Bounded prefix/suffix matching; ignore case and edge whitespace only.
        # Prefer exact names so a known variant keeps its specific description.
        key=text.strip().upper()
        if not key:return []
        exact=self.records.get(key)
        if exact:
            return [dict(record,match_type='exact') for record in exact]
        if numeric_prefix and rule_enabled('match.numeric_family') and re.fullmatch(r'[0-9]{4,}', key):
            return self.numeric_family(key)
        if automatic_exclusion(key) or key.isdigit() or not rule_enabled('match.affixes'):return []  # Numeric aliases must be exact.
        # Production catalogues are immutable and indexed before publication.
        # Lazy construction also supports small in-memory test catalogues.
        if (getattr(self, '_indexed_records', None) is not self.records or
                getattr(self, '_indexed_count', -1) != len(self.records)):
            self.build_index()
        cache = self._partial_cache
        with self._cache_lock:
            if key in cache:
                cache.move_to_end(key)
                return cache[key]
        names = set(self._affix_index.get(key, ()))
        # The OCR string can itself have up to three extra characters per side.
        for left in range(MAX_AFFIX_CHARS+1):
            for right in range(MAX_AFFIX_CHARS+1):
                if left+right < len(key):
                    name = key[left:len(key)-right if right else None]
                    if name in self.records:
                        names.add(name)
        # Show the closest, most specific names first; retain ambiguous sources.
        names=sorted(names,key=lambda name:(abs(len(name)-len(key)),-len(name),name))
        result = [dict(record,match_type='partial')
                  for name in names for record in self.records[name]]
        with self._cache_lock:
            cache[key] = result
            cache.move_to_end(key)
            while len(cache) > 2048:
                cache.popitem(last=False)
        return result

    def correction_matches(self, text):
        from confusion_matching import matches
        return matches(self, text)

    def numeric_family(self, key):
        """Names that are a letter prefix + these digits + a short suffix (2904 -> LM2904DT).

        Used only for numeric markings printed on a detected IC body. Letters may
        only be added in front; the printed digits are never changed or extended.
        """
        if (getattr(self, '_indexed_records', None) is not self.records or
                getattr(self, '_indexed_count', -1) != len(self.records)):
            self.build_index()
        if MAX_AFFIX_CHARS < 1 or not rule_enabled('match.numeric_family'):
            # 0.8.8: affix matching disabled; {1,0} would be an invalid regex.
            return []
        pattern = _numeric_family_pattern(key)
        names = sorted({name for name in self._affix_index.get(key, ()) if pattern.match(name)},
                       key=lambda name: (len(name), name))
        return [dict(record, match_type='partial') for name in names for record in self.records[name]]


@lru_cache(maxsize=1024)
def _numeric_family_pattern(key):
    return re.compile(r'^[A-Z]{1,%d}%s[A-Z][A-Z0-9-]{0,%d}$|^[A-Z]{1,%d}%s$'
                      % (MAX_AFFIX_CHARS, key, MAX_AFFIX_CHARS-1, MAX_AFFIX_CHARS, key))


def family_hint(text):
    pattern = part_pattern(text)
    if pattern:
        return pattern + ' — pattern only'
    from marking_rules import HINT_PATTERNS
    for label, pattern in HINT_PATTERNS:
        if pattern.fullmatch(text.upper()):
            return label + ' — pattern only'
    return ''

def joined_markings(rows, catalog):
    """Join a wrapped part number only with spatial and catalogue evidence."""
    if catalog is None or not rule_enabled('join.wrapped'):
        return []
    import numpy as np
    joined = []
    seen = {r['key'] for r in rows}
    # Work is bounded; retain source tokens for diagnostics and manual review.
    for first in rows[:64]:
        if (not re.fullmatch(r'[A-Z]{2,8}[0-9]{1,6}', first['key']) or
                first.get('conflicts') or not first.get('box')):
            continue
        a = np.asarray(first['box'], dtype=float)
        direction = a[1] - a[0]
        width = float(np.linalg.norm(direction))
        if width < 1:
            continue
        u = direction / width
        v = np.array([-u[1], u[0]])
        height = float(np.ptp(a @ v))
        for second in rows[:64]:
            if (second is first or second.get('rotation') != first.get('rotation') or
                    second.get('conflicts') or not second.get('box') or
                    not re.fullmatch(r'[0-9]{1,4}[A-Z]{1,4}', second['key'])):
                continue
            b = np.asarray(second['box'], dtype=float)
            bh = float(np.ptp(b @ v))
            bw = float(np.ptp(b @ u))
            delta = b.mean(axis=0) - a.mean(axis=0)
            if (height < 1 or not tuning('component_catalog.wrapped_height_min') <= bh / height <= 2 or
                    not tuning('component_catalog.wrapped_vertical_min') * height <= delta @ v <= 3 * height or
                    abs(delta @ u) > tuning('component_catalog.wrapped_horizontal_ratio') * max(width, bw)):
                continue
            key = first['key'] + second['key']
            if key in seen:
                continue
            matches = catalog.find(key)
            names = {m['part'].upper() for m in matches}
            if not matches or (not any(m.get('match_type') == 'exact' for m in matches)
                               and len(names) != 1):
                continue
            # A partial match may remove a printed suffix, never guess missing text.
            if not any(m.get('match_type') == 'exact' or key.startswith(m['part'].upper())
                       for m in matches):
                continue
            points = np.vstack([a, b])
            left, right = (points @ u).min(), (points @ u).max()
            top, bottom = (points @ v).min(), (points @ v).max()
            box = [(u*x + v*y).tolist() for x,y in
                   [(left,top),(right,top),(right,bottom),(left,bottom)]]
            joined.append(dict(first, key=key, text=key, box=box,
                score=min(first.get('score',0), second.get('score',0)),
                rank=min(first.get('rank',0), second.get('rank',0)) + tuning('component_catalog.wrapped_rank_bonus'),
                status='Joined printed lines — identity unverified',
                evidence='Adjacent aligned lines: '+first['key']+' + '+second['key'],
                joined_from=[first['key'],second['key']],
                observed_markings=[first.get('raw_text', first.get('text', first['key'])),
                                   second.get('raw_text', second.get('text', second['key']))]))
            seen.add(key)
    return joined


def joined_fragments(rows, catalog):
    """Pieces of one printed line read as separate boxes (0.8.3.5).

    Same reading direction and baseline, similar height, the second starting
    where the first ends (a gap of up to 1.2 line heights, or an overlap that
    re-reads 1-2 characters: TLE723 + 38SL -> TLE7238SL). Only joins with
    trusted database support are offered; the pieces stay listed.
    """
    if catalog is None or not rule_enabled('join.fragments'):
        return []
    import numpy as np
    pieces = [r for r in rows[:64] if r.get('box') and not r.get('conflicts') and
              not r.get('exclusion_reason') and r.get('score', 0) >= tuning('component_catalog.fragment_min_score') and len(r['key']) >= 2]
    seen = {r['key'] for r in rows}
    joined = []
    for first in pieces:
        a = np.asarray(first['box'], dtype=float)
        if a.shape != (4, 2):
            continue
        direction = a[1] - a[0]
        width = float(np.linalg.norm(direction))
        if width < 1:
            continue
        u = direction / width
        v = np.array([-u[1], u[0]])
        height = float(np.ptp(a @ v))
        if height < 1:
            continue
        for second in pieces:
            if second is first:
                continue
            b = np.asarray(second['box'], dtype=float)
            if b.shape != (4, 2):
                continue
            other = b[1] - b[0]
            length = float(np.linalg.norm(other))
            if length < 1 or float(np.dot(u, other / length)) < tuning('component_catalog.fragment_alignment_cosine'):
                continue
            if not tuning('component_catalog.fragment_height_min') <= float(np.ptp(b @ v)) / height <= tuning('component_catalog.fragment_height_max'):
                continue
            if abs(float((b.mean(axis=0) - a.mean(axis=0)) @ v)) > tuning('component_catalog.fragment_baseline_height_ratio') * height:
                continue
            gap = float((b @ u).min() - (a @ u).max())
            if (b @ u).min() <= (a @ u).min() or not -tuning('component_catalog.fragment_overlap_limit') * height <= gap <= tuning('component_catalog.fragment_gap_limit') * height:
                continue
            for overlap in (0, 1, 2):
                if overlap and not first['key'].endswith(second['key'][:overlap]):
                    continue
                key = first['key'] + second['key'][overlap:]
                if key in seen or len(key) < 5:
                    continue
                trusted = trusted_matches(catalog.find(key), key)
                if not trusted:
                    continue
                points = np.vstack([a, b])
                left, right = (points @ u).min(), (points @ u).max()
                top, bottom = (points @ v).min(), (points @ v).max()
                box = [(u*x + v*y).tolist() for x, y in [(left, top), (right, top), (right, bottom), (left, bottom)]]
                raw = (first.get('raw_text', first.get('text', first['key'])) + ' ' +
                       second.get('raw_text', second.get('text', second['key'])))
                joined.append(dict(first, key=key, text=key, raw_text=raw, box=box, conflicts=[],
                    score=min(first.get('score', 0), second.get('score', 0)),
                    rank=min(first.get('rank', 0), second.get('rank', 0)) + tuning('component_catalog.fragment_rank_bonus'),
                    orientation_alternative=bool(first.get('orientation_alternative') or second.get('orientation_alternative')),
                    status='Joined fragments of one printed line — identity unverified',
                    evidence='Same line: ' + first['key'] + ' + ' + second['key'] +
                             (f' (shared {second["key"][:overlap]})' if overlap else ''),
                    joined_from=[first['key'], second['key']], fragment_join=True,
                    observed_markings=[first.get('raw_text', first['key']), second.get('raw_text', second['key'])]))
                seen.add(key)
                break
    return joined


def logo_stripped(rows, catalog):
    """A logo read as 1-2 leading letters (MNCV7356G -> NCV7356G; 0.8.3.5).

    Offered only when the reading itself has no trusted database support and the
    remainder (5+ characters, letters and digits) has.
    """
    if catalog is None or not rule_enabled('join.logo'):
        return []
    out, seen = [], {r['key'] for r in rows}
    for row in rows[:64]:
        key = row['key']
        if (len(key) < 6 or not key[0].isalpha() or row.get('exclusion_reason') or
                row.get('score', 0) < tuning('component_catalog.logo_min_score') or trusted_matches(catalog.find(key), key)):
            continue
        for n in (1, 2):
            rest = key[n:]
            if (not key[:n].isalpha() or len(rest) < 5 or rest in seen or
                    not (any(c.isalpha() for c in rest) and any(c.isdigit() for c in rest))):
                continue
            if trusted_matches(catalog.find(rest), rest):
                out.append(dict(row, key=rest, text=rest, logo_stripped_from=key,
                    status='Leading logo character(s) removed — identity unverified',
                    evidence=f'{key[:n]} before {rest} read as text; {rest} matches the database',
                    observed_markings=[row.get('raw_text', row.get('text', key))]))
                seen.add(rest)
                break
    return out


def trusted_matches(matches, text):
    """Automatic identity evidence; generic substring hits remain suggestions.

    A literal printed base plus 1–3 suffix letters may resolve the base identity.
    Missing prefixes, numeric-only aliases and arbitrary affix removal cannot.
    This validates the base name only, never a complete orderable SKU.
    """
    key=text.strip().upper()
    exact=[m for m in matches if m.get('match_type') in ('exact','verified_alias','abbreviated','family_suffix') or
           (m.get('match_type') == 'corrected' and m.get('correction_eligible'))]
    if exact:
        names={m['part'].strip().upper() for m in exact}
        return exact if len(names)==1 else []
    if not rule_enabled('match.literal_suffix'):
        return []
    from marking_rules import PATTERNS
    strict_family=any(pattern.fullmatch(key) for _, pattern in PATTERNS)
    bases=[]
    for m in matches:
        if m.get('match_type') == 'rule_candidate':
            continue
        part=m['part'].strip().upper()
        # 0.8.9.4: a numeric-only base (7805 in 7805A) is accepted only when the
        # printed text matches a strict device-family rule (e.g. 78/79 regulators).
        literal_base = len(part)>=5 and any(c.isalpha() for c in part) and any(c.isdigit() for c in part)
        numeric_base = len(part)>=4 and part.isdigit() and strict_family
        if ((literal_base or numeric_base)
                and key.startswith(part) and re.fullmatch(r'[A-Z]{1,3}', key[len(part):])):
            bases.append(dict(m, identity_evidence='literal_base_with_suffix'))
    return bases if len({m['part'].strip().upper() for m in bases})==1 else []


def printed_family_evidence(matches, text):
    """A full part-like printed prefix can justify waiting, not guessing a SKU."""
    key=text.strip().upper()
    if not rule_enabled('match.printed_family'):
        return False
    if len(key)<5 or not re.match(r'^(?:[A-Z]{2,6}[0-9]|(?:74|54)[A-Z])',key):
        return False
    return any(m['part'].upper().startswith(key) and
               re.fullmatch(r'[A-Z]{1,3}',m['part'].upper()[len(key):]) for m in matches)


def correction_matches(catalog, text):
    method = getattr(type(catalog), 'correction_matches', None)
    return method(catalog, text) if callable(method) else []


def resolved_matches(catalog, text):
    literal = trusted_matches(catalog.find(text), text)
    if not literal:
        from marking_aliases import matches
        literal = matches(catalog, text)
    return literal or trusted_matches(correction_matches(catalog, text), text)


def annotate(rows,catalog=None):
    result=[]
    rows = list(rows)
    originals = [r for r in rows if not (r.get('fragment_join') or r.get('logo_stripped_from'))]
    present = {r['key'] for r in rows}
    # Derived rows already present (re-annotation) are kept, not derived again.
    extra = joined_markings(rows, catalog) + [r for r in joined_fragments(originals, catalog) +
                                              logo_stripped(originals, catalog) if r['key'] not in present]
    for original in rows + extra:
        row=dict(original)
        # Match the actual OCR token, not a punctuation-stripped key.
        text=row.get('text',row['key'])
        raw = row.get('raw_text', text).strip()
        # Retain significant decimal points lost by OCR token normalization.
        if '.' in raw and re.fullmatch(r'[A-Za-z0-9. -]+', raw) and re.sub(r'[^A-Z0-9-]', '', raw.upper()) == row['key']:
            text = raw
            row['text'] = raw
        row['exclusion_reason'] = origin_exclusion(text) or (
            '' if row.get('ic_numeric') else automatic_exclusion(text))
        if catalog is None or row['exclusion_reason']:
            row['database_matches']=[]
        elif row.get('ic_numeric'):
            row['database_matches']=catalog.find(text, numeric_prefix=True)
        else:
            row['database_matches']=catalog.find(text)
        row.pop('ocr_correction', None)
        row['applied_rules'] = []
        if catalog is not None and not row['exclusion_reason'] and not any(m.get('match_type') == 'exact' for m in row['database_matches']):
            from marking_aliases import matches as alias_matches
            aliases = alias_matches(catalog, text)
            if aliases:
                row['database_matches'] = aliases
                row['applied_rules'] = [aliases[0]['applied_rule']]

        if catalog is not None and not origin_exclusion(text) and not any(
                m.get('match_type') in ('exact', 'abbreviated', 'family_suffix') for m in row['database_matches']):
            from prefix_rules import matches as prefix_matches
            candidates = prefix_matches(catalog, text)
            if row['exclusion_reason']:
                candidates = [m for m in candidates if m['applied_rule']['rule_id'] == 'transistor.missing_2s']
            if candidates:
                row['database_matches'] = candidates
                row['applied_rules'] = [dict(candidates[0]['applied_rule'],
                    candidate_count=len({m['part'] for m in candidates}))]
                row['status'] = text + ' — possible database matches; identity unverified'

        row['correction_suggestions'] = []
        trusted = trusted_matches(row['database_matches'], text)
        if (catalog is not None and not row['exclusion_reason'] and not trusted and
                not any(m.get('match_type') == 'rule_candidate' for m in row['database_matches'])):
            suggestions = correction_matches(catalog, text)
            row['correction_suggestions'] = suggestions
            # 0.8.3.5: up to 3 substitutions, cost limits in confusion_matching.
            if row.get('score',0) >= CORRECTION_MIN_SCORE and not row.get('orientation_alternative'):
                accepted = trusted_matches(suggestions,text)
                if accepted:
                    row['database_matches'] = accepted
                    row['ocr_correction'] = dict(accepted[0]['correction'])
                    trusted = trusted_matches(accepted, text)
        if not row['applied_rules'] and not row.get('ocr_correction'):
            if any(m.get('identity_evidence') == 'literal_base_with_suffix' for m in trusted):
                row['applied_rules'].append(dict(rule_id='legacy.literal_base_suffix', observed=text))
        for flag, rule_id in (('logo_stripped_from','legacy.logo_strip'), ('joined_from','legacy.join_printed_fragments')):
            if row.get(flag):
                row['applied_rules'].append(dict(rule_id=rule_id, observed=row.get('observed_markings', []), result=text))
        if row.get('whitespace_joined'):
            row['applied_rules'].append(dict(rule_id='legacy.whitespace_join', observed=row.get('raw_text', text), result=text))
        row['database_family_evidence']=printed_family_evidence(row['database_matches'],text)
        row['trusted_database_matches']=trusted
        names = {m['part'].strip().upper() for m in row['trusted_database_matches']}
        # Preserve the OCR conflict in diagnostics. It need not block a database
        # selection when every observed spelling resolves to the same parts
        # (e.g. MC145406DW / MC145406DU against an MC145406 base entry).
        row['database_identity_consistent'] = bool(
            row.get('conflicts') and bool(names) and catalog is not None and
            all({m['part'].strip().upper() for m in resolved_matches(catalog,other)} == names
                for other in row['conflicts']))
        row['selected_database_match'] = choose_match(row['trusted_database_matches'], text)
        row['database_ambiguous'] = database_ambiguous(row['database_matches'])
        row['function_summary']=function_summary(row['trusted_database_matches'], row['selected_database_match'])
        row['family_hint']=family_hint(text)
        row['part_pattern'] = part_pattern(row['key'])
        # A lone W prefix plus digits is too broad to outrank a supported
        # block marking. It remains a candidate, never a hard exclusion.
        row['weak_family_hint'] = bool(row.get('kind') == 'family' and
            re.fullmatch(r'W[0-9]+[A-Z]{0,2}', row['key']) and not row['part_pattern'])
        row['observed_markings'] = list(row.get('observed_markings') or
            [row.get('raw_text', text)])
        row['resolved_partnumber'] = (row['selected_database_match'] or {}).get('part', '')
        if row['applied_rules'] and 'label' in row['applied_rules'][0]:
            row['status'] = row['applied_rules'][0]['label'] + ' — ' + row['resolved_partnumber'] + ' from ' + text
        if row.get('ocr_correction'):
            row['applied_rules'].append(dict(rule_id='ocr.bounded_confusion', **row['ocr_correction']))
            row['status'] = 'OCR correction — '+row['resolved_partnumber']+' from '+text
        row['selection_tier'] = ('database' if row['trusted_database_matches'] else
                                 'part_pattern' if row['part_pattern'] else
                                 'family' if row.get('kind') == 'family' else
                                 'numeric' if row['key'].isdigit() else 'unverified')
        row['display_rank']=row.get('rank',0)+(tuning('ranking.database_bonus') if row['trusted_database_matches'] else 0)
        result.append(row)
    # Geometry views are read-only inputs to the neighbour search; build once.
    expanded = expand_views(result)
    for row in result:
        row['context_marking'] = contextual_marking(row, result, expanded)
        row['selection_rank'] = row.get('rank', 0) + context_rank_bonus(row)
        if row['context_marking'] and not row['trusted_database_matches']:
            row['selection_tier'] = 'context_marking'
            row['status'] = 'Printed marking in aligned block — identity unknown'
    # A recogniser's larger score is not proof of the reading direction. Allow
    # a strong, bounded part syntax to compete with reverse-direction junk.
    # Never resolve two plausible part readings or a character conflict here.
    from ocr_core import same_text_region
    for row in result:
        row['orientation_pattern_supported'] = False
        if (not rule_enabled('orientation.pattern') or not row.get('orientation_alternative') or not row.get('part_pattern') or
                row.get('score', 0) < ORIENTATION_PATTERN_MIN_SCORE or
                not row.get('box') or row.get('conflicts')):
            continue
        opposite = [other for other in result if other is not row and other.get('box') and
                    not other.get('orientation_alternative') and
                    (other.get('rotation', 0) - row.get('rotation', 0)) % 360 == 180 and
                    same_text_region(row['box'], other['box'])]
        if opposite and all(not (other.get('part_pattern') or other.get('kind') == 'family' or
                                  other.get('trusted_database_matches')) and
                            other.get('score', 0) - row.get('score', 0) <= ORIENTATION_PATTERN_MAX_SCORE_GAP
                            for other in opposite):
            row['orientation_pattern_supported'] = True
    return sorted(result,key=lambda r:(
        any(m.get('match_type')=='exact' for m in r['trusted_database_matches']),
        bool(r['trusted_database_matches']),bool(r['part_pattern']),
        r.get('kind') == 'family' and not r.get('weak_family_hint'),
        *selection_order(r), r['display_rank']),reverse=True)

def describe(matches):
    if not matches:return 'No database name match.'
    kind=('Abbreviated marking' if any(r.get('match_type')=='abbreviated' for r in matches) else
          'Package suffix' if any(r.get('match_type')=='family_suffix' for r in matches) else
          'Corrected OCR' if any(r.get('match_type')=='corrected' for r in matches) else
          'Partial' if any(r.get('match_type')=='partial' for r in matches) else 'Exact')
    lines=[kind+' database name match — source-listed, identity unverified.']
    if database_ambiguous(matches):
        lines.append('* Multiple database variants/descriptions; one representative is displayed. All matches follow.')
    for r in matches:
        lines.append(f"{r['part']} | {r['manufacturer'] or 'manufacturer not stated'}\n"
            f"{r['source']} line {r['line']} | package/interface: {r['package'] or 'not stated'}"
            +(f" | {r['qualifiers']}" if r['qualifiers'] else '')
            +'\nSource-entry function: '+(r.get('entry_function') or 'not recorded')
            +'\nComponent function: '+(r.get('component_function') or 'not recorded'))
    return '\n\n'.join(lines)


def functions(matches):
    return sorted({value.strip() for r in matches
                   for value in (r.get('entry_function'),r.get('component_function'))
                   if value and value.strip()})


def choose_match(matches, text=''):
    """Choose a stable representative, independent of database insertion order."""
    key = text.strip().upper()
    def order(record):
        part = record['part'].strip().upper()
        description = record_description(record)
        return (record.get('match_type') != 'exact', abs(len(part)-len(key)),
                -len(part), part, not bool(description.strip()),
                ' '.join(description.split()).casefold(),
                str(record.get('manufacturer') or ''), str(record.get('source') or ''),
                str(record.get('line') or ''))
    return min(matches, key=order) if matches else None


def record_description(record):
    return next((' '.join((record.get(key) or '').split())
                 for key in ('entry_function', 'component_function')
                 if (record.get(key) or '').strip()), '')


def database_ambiguous(matches):
    names = {m['part'].strip().upper() for m in matches}
    descriptions = {' '.join(value.split()).casefold() for value in functions(matches)}
    return len(names) > 1 or len(descriptions) > 1


def function_summary(matches, selected=None):
    if not matches:
        return ''
    selected = selected or choose_match(matches)
    value = record_description(selected) or 'Function not recorded'
    return ' '.join(value.split()) + (' *' if database_ambiguous(matches) else '')


def live_candidates(rows, catalog=None, *, annotated=False):
    """Exact/base evidence takes priority; generic suggestions never veto.

    Trusted exact/base evidence may remain pending to avoid locking a lot code.
    Generic substring suggestions never suppress an unmatched marking.
    """
    candidates=[]
    annotated=list(rows) if annotated else annotate(rows,catalog)
    pending_identity=any((r.get('trusted_database_matches') or r.get('database_family_evidence')) and r.get('box') and not r.get('exclusion_reason') and r.get('score',0)>=tuning('component_catalog.pending_database_score') for r in annotated)
    pending_conflict = any(r.get('conflicts') and not r.get('database_identity_consistent') and
                           r.get('kind') in ('family', 'unknown') and r.get('score', 0) >= tuning('component_catalog.pending_conflict_score') and
                           r.get('box') and not r.get('exclusion_reason') and
                           not r.get('orientation_alternative') for r in annotated)
    for row in annotated:
        row['selection_block_reason'] = ''
        matches=row.get('trusted_database_matches', [])
        if (row.get('exclusion_reason') or not row.get('box') or
                (row.get('conflicts') and not row['database_identity_consistent'])):
            continue
        if (row.get('orientation_alternative') and not matches and
                not row.get('orientation_pattern_supported')):
            continue
        if pending_identity and not matches and not row.get('database_family_evidence'):continue
        if pending_conflict and row['key'].isdigit() and not matches:
            row['selection_block_reason'] = 'Unresolved identifier conflict — numeric fallback withheld'
            continue
        exact=any(m.get('match_type') in ('exact','verified_alias') for m in matches)
        threshold=tuning('selection.exact_min_score') if exact else tuning('selection.other_min_score')
        if row['key'].isdigit():threshold=max(threshold,tuning('selection.numeric_min_score'))
        if row.get('score',0)<threshold:continue
        candidates.append(row)
    # Context is screened here as well as in scan_result, so a nonselectable
    # suggestion cannot hide a valid fallback in early-accept/retry callers.
    candidates=[r for r in candidates if r.get('kind')!='context' or
                r.get('context_marking') or r.get('trusted_database_matches')]
    if any(r.get('trusted_database_matches') for r in candidates):
        candidates=[r for r in candidates if r.get('trusted_database_matches')]
    return sorted(candidates,key=lambda r:(
        any(m.get('match_type') in ('exact','verified_alias') for m in r.get('trusted_database_matches',[])),
        bool(r.get('trusted_database_matches')),bool(r.get('part_pattern')),
        r.get('kind') == 'family' and not r.get('weak_family_hint'),
        *selection_order(r), r.get('score',0)),reverse=True)
