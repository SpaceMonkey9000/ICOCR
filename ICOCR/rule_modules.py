"""Data-only rule modules. Loaded once; no executable plugins or scan-time I/O."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from collections import Counter

SCHEMA_VERSION = 1
FAMILY_FILE = 'rules/device_families.json'
FAMILY_LISTS = ('strict_patterns', 'spaced_patterns', 'broad_patterns', 'hint_patterns', 'contextual_costs')
GROUPS = {
    'rules/part_prefixes.json': ('syntax.prefixes', 'Part-number prefixes', 'Syntax'),
    'rules/negative_words.json': ('exclude.metadata', 'Country, origin and metadata words', 'Exclusions'),
    'rules/brands.json': ('ranking.brands', 'Manufacturer and logo words', 'Ranking'),
    'rules/ocr_confusions.json': ('ocr.confusions', 'Bounded OCR character corrections', 'OCR correction'),
    'rules/marking_aliases.json': ('logic.aliases', '74-series abbreviations and package suffixes', 'Matching'),
    'ranking/line_weights.json': ('ranking.lines', 'Context and geometry line ranking', 'Ranking'),
}
SWITCHES = {
    'match.affixes': ('Bounded prefix/suffix suggestions', 'Matching'),
    'match.numeric_family': ('Numeric marking family suggestions', 'Matching'),
    'match.literal_suffix': ('Printed part plus letter suffix', 'Matching'),
    'match.printed_family': ('Printed family evidence', 'Matching'),
    'match.ordering_suffix': ('Ordering-code suffix after a hyphen (-I/SO, -PU)', 'Matching'),
    'join.wrapped': ('Join wrapped part-number lines', 'Joining'),
    'join.fragments': ('Join fragments of one printed line', 'Joining'),
    'join.logo': ('Remove leading logo characters', 'Joining'),
    'exclude.numeric': ('Exclude short numeric values', 'Exclusions'),
    'exclude.repeated': ('Exclude repeated-character noise', 'Exclusions'),
    'exclude.pcb_reference': ('Exclude PCB reference designators', 'Exclusions'),
    'exclude.resistor_codes': ('Exclude resistor letter codes (4R7, 01C)', 'Exclusions'),
    'context.block': ('Aligned marking-block support', 'Context'),
    'context.lot_penalty': ('Lot/date-code ranking penalty', 'Context'),
    'context.short_penalty': ('Short marking-block ranking penalty', 'Context'),
    'context.rank_bonus': ('Part-like marking-block preference', 'Context'),
    'orientation.pattern': ('Part-syntax reading-direction support', 'Syntax'),
}


def rules_directory():
    from project_paths import DATA
    return Path(os.environ.get('ICOCR_RULES_DIR') or DATA/'rules').expanduser().resolve()


def module(rule_id, name, category, kind, **fields):
    return dict(schema_version=1, id=rule_id, name=name, category=category,
                enabled=True, kind=kind, priority=100, **fields)


def default_modules(config):
    result = []
    for target, (rule_id, name, category) in GROUPS.items():
        row = module(rule_id, name, category, 'config', target=target, config=copy.deepcopy(config[target]))
        if 'enabled' in row['config']:
            row['enabled'] = row['config']['enabled']
        result.append(row)
    for collection in FAMILY_LISTS:
        for index, item in enumerate(config[FAMILY_FILE][collection]):
            item = copy.deepcopy(item)
            enabled = item.pop('enabled')
            labels = {
                'spaced_patterns': ['Join spaced 74/54 logic names', 'Join spaced LM names',
                    'Join spaced BTS/BTT/BTF names', 'Join spaced SP interface names',
                    'Join spaced LA names', 'Join spaced Darlington array names', 'Join spaced serial memory names'],
                'broad_patterns': ['Broad logic-family syntax', 'Broad memory-family syntax', 'Broad T-family syntax'],
                'contextual_costs': ['Lower OCR correction cost for logic-family T'],
            }
            friendly = labels[collection][index] if index < len(labels.get(collection, [])) else collection.replace('_', ' ').capitalize()+': '+item['id']
            row = module('family.'+collection+'.'+item['id'],
                         item.get('label') or friendly,
                         'Device families', 'family', collection=collection, rule=item)
            row['enabled'] = enabled
            row['priority'] = 100 + index
            result.append(row)
    for rule_id, (name, category) in SWITCHES.items():
        if rule_id == 'orientation.pattern':
            result.append(module(rule_id, name, category, 'orientation',
                min_score=config[FAMILY_FILE]['orientation_min_score'],
                max_score_gap=config[FAMILY_FILE]['orientation_max_score_gap']))
        else:
            result.append(module(rule_id, name, category, 'switch'))
    result.append(module('mosfet.short_marking', 'Short MOSFET markings (50N06 etc.)',
                         'Matching', 'prefix_candidates', pattern=r'[0-9]{2,3}[NP][0-9]{2,3}',
                         prefixes=['CS', 'DFP', 'FQP', 'HFP', 'MTP', 'RFP'],
                         suffixes=['', 'L'], ignore_trailing_hyphen=True))
    result.extend(additional_modules())
    return result


def additional_modules():
    specs = [
        ("syntax.additional_prefixes", "Additional literal part prefixes", "prefix_hints", "TLE ADM UCC INA ADUM ISO DRV TSV TDA NJM STP IPP STF IRFB IPA IXTP TK FDP FQP FQPF FDPF FCP SPP"),
        ("logic.additional_abbreviations", "Additional 74-series abbreviations", "logic", "LS ALS F AC ACT AHC AHCT LVC"),
        ("transistor.missing_2s", "Missing 2S transistor prefix", "transistor", "A B C D J K"),
        ("mosfet.database_stems", "Database-backed short MOSFET markings", "mosfet", ""),
        ("match.separator_recovery", "Missing hyphens and spaces", "separators", ""),
    ]
    return [module(i, n, "Syntax" if k == "prefix_hints" else "Matching",
                   "database_rule", recipe=k, values=v.split()) for i, n, k, v in specs]


def write_atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.'+path.name, suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write('\n')
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)



def validate_module(row, validate_config, base):
    if not isinstance(row, dict):
        raise ValueError('expected a rule object')
    required = {'schema_version', 'id', 'name', 'category', 'enabled', 'kind'}
    if not required <= row.keys():
        raise ValueError('missing fields: '+', '.join(sorted(required-row.keys())))
    if type(row['schema_version']) is not int or row['schema_version'] != 1:
        raise ValueError('unsupported schema_version')
    if not isinstance(row['id'], str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', row['id']):
        raise ValueError('invalid rule ID')
    for key in ('name', 'category'):
        if not isinstance(row[key], str) or not 1 <= len(row[key].strip()) <= 200:
            raise ValueError('invalid '+key)
    if type(row['enabled']) is not bool:
        raise ValueError('enabled must be boolean')
    kind = row['kind']
    extras = {'database_rule': {'recipe', 'values'}, 'config': {'target', 'config'}, 'family': {'collection', 'rule'},
              'switch': set(), 'orientation': {'min_score', 'max_score_gap'}, 'prefix_candidates': {'pattern', 'prefixes', 'suffixes', 'ignore_trailing_hyphen'}}
    if kind not in extras or set(row) - {'priority'} != required | extras[kind]:
        raise ValueError('unsupported kind or unexpected fields')
    if 'priority' in row and (type(row['priority']) is not int or not -10000 <= row['priority'] <= 10000):
        raise ValueError('priority must be an integer between -10000 and 10000')
    row = copy.deepcopy(row)
    if kind == 'database_rule':
        allowed = {'prefix_hints': None, 'logic': {'LS','ALS','F','AC','ACT','AHC','AHCT','LVC'},
                   'transistor': set('ABCDJK'), 'mosfet': set(), 'separators': set()}
        recipe, values = row['recipe'], row['values']
        if not isinstance(recipe, str) or recipe not in allowed:
            raise ValueError('unknown database recipe')
        if (not isinstance(values, list) or len(values) > 64 or
                any(not isinstance(v, str) or not re.fullmatch(r'[A-Z]{1,8}', v) for v in values) or
                len(values) != len(set(values)) or
                (allowed[recipe] is not None and not set(values) <= allowed[recipe])):
            raise ValueError('invalid recipe values')
    elif kind == 'config':
        if row['target'] not in GROUPS:
            raise ValueError('unsupported configuration target')
        row['config'] = validate_config(row['target'], row['config'])
    elif kind == 'family':
        if row['collection'] not in FAMILY_LISTS or not isinstance(row['rule'], dict):
            raise ValueError('invalid family collection or rule')
        probe = copy.deepcopy(base[FAMILY_FILE])
        probe[row['collection']] = [dict(row['rule'], enabled=row['enabled'])]
        validate_config(FAMILY_FILE, probe)
    elif kind == 'switch':
        if row['id'] not in SWITCHES:
            raise ValueError('unknown built-in operation')
    elif kind == 'orientation':
        if row['id'] != 'orientation.pattern':
            raise ValueError('orientation module must use orientation.pattern ID')
        for key in ('min_score', 'max_score_gap'):
            if type(row[key]) not in (int, float) or not 0 <= row[key] <= 1:
                raise ValueError(key+' must be between zero and one')
    else:
        if (not isinstance(row['pattern'], str) or len(row['pattern']) > 256 or
                not re.fullmatch(r'[A-Za-z0-9\[\]{}?,\\+.-]+', row['pattern'])):
            raise ValueError('use a bounded character-class pattern; groups, alternation and wildcards are unsupported')
        pattern = re.compile(row['pattern'])
        # Bounded inputs and no grouping/alternation prevent nested-regex backtracking.
        if pattern.fullmatch(''):
            raise ValueError('pattern must not match empty text')
        for key in ('prefixes', 'suffixes'):
            values = row[key]
            if (not isinstance(values, list) or not 1 <= len(values) <= 64 or
                    any(not isinstance(v, str) or not re.fullmatch(r'[A-Z]{1,8}' if key == 'prefixes' else r'[A-Z]{0,4}', v) for v in values) or
                    len(set(values)) != len(values)):
                raise ValueError('invalid '+key)
        if type(row['ignore_trailing_hyphen']) is not bool:
            raise ValueError('ignore_trailing_hyphen must be boolean')
    return row


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError('duplicate JSON key: '+key)
        out[key] = value
    return out


class RuleSnapshot:
    def __init__(self, directory, base, validate_config):
        self.directory = Path(directory)
        self.modules, self.errors = [], []
        self.config = copy.deepcopy(base)
        disk = self.directory.exists()
        source = []
        if disk:
            for path in sorted(self.directory.glob('*.json')):
                try:
                    with path.open('rb') as handle:
                        raw = handle.read(1024*1024+1)
                    if len(raw) > 1024*1024:
                        raise ValueError('rule exceeds 1 MiB')
                    row = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_pairs,
                                     parse_constant=lambda x: (_ for _ in ()).throw(ValueError('non-finite number')))
                    source.append((path, validate_module(row, validate_config, base)))
                except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
                    self.errors.append(dict(file=str(path), error=str(exc)))
        else:
            source = [(self.directory/(row['id']+'.json'), validate_module(row, validate_config, base))
                      for row in default_modules(base)]
        source.sort(key=lambda item: (item[1].get('priority', 100), item[1]['id'], str(item[0])))
        ids = Counter(row['id'] for _, row in source)
        targets = Counter(row['target'] for _, row in source if row['kind'] == 'config')
        family_keys = Counter((row['collection'], row['rule']['id']) for _, row in source if row['kind'] == 'family')
        for path, row in source:
            duplicate = (ids[row['id']] > 1 or
                         (row['kind'] == 'config' and targets[row['target']] > 1) or
                         (row['kind'] == 'family' and family_keys[(row['collection'], row['rule']['id'])] > 1))
            if duplicate:
                self.errors.append(dict(file=str(path), error='duplicate rule ID, configuration target or family ID; all conflicting modules skipped'))
            else:
                self.modules.append(dict(row, path=str(path)))
        # Once migrated, deleted/invalid modules must never reactivate legacy rules.
        for target in GROUPS:
            self._disable(target)
        for name in FAMILY_LISTS:
            self.config[FAMILY_FILE][name] = []
        self.switches = {key: False for key in SWITCHES}
        for row in self.modules:
            kind, enabled = row['kind'], row['enabled']
            if kind == 'config':
                self.config[row['target']] = copy.deepcopy(row['config'])
                if enabled:
                    if 'enabled' in self.config[row['target']]:
                        self.config[row['target']]['enabled'] = True
                else:
                    self._disable(row['target'])
            elif kind == 'family':
                self.config[FAMILY_FILE][row['collection']].append(dict(row['rule'], enabled=enabled))
            elif kind in ('switch', 'orientation'):
                self.switches[row['id']] = enabled
                if kind == 'orientation':
                    self.config[FAMILY_FILE]['orientation_min_score'] = row['min_score']
                    self.config[FAMILY_FILE]['orientation_max_score_gap'] = row['max_score_gap']
        self.sha256 = hashlib.sha256(json.dumps([
            {k:v for k,v in row.items() if k != 'path'} for row in self.modules],
            sort_keys=True, allow_nan=False).encode()).hexdigest()

    def _disable(self, target):
        data = self.config[target]
        if target.endswith('part_prefixes.json'):
            data['prefixes'] = []
        elif target.endswith('negative_words.json'):
            for name in ('origin_words', 'origin_phrases', 'extra_exact'):
                data[name] = []
        elif target.endswith('brands.json'):
            data['brands'] = {}
        elif target.endswith('ocr_confusions.json'):
            data['pairs'], data['suffix_letters'], data['max_suffix'] = [], {}, 0
        elif 'enabled' in data:
            data['enabled'] = False

    def enabled(self, rule_id):
        return self.switches.get(rule_id, False)


def save_enabled(rows, values, validate_config, base):
    """Validate and stage all changes before atomic per-file replacements.

    A failure rolls back completed writes; stale editor snapshots are rejected.
    """
    updates = []
    for original in rows:
        wanted = values[original['id']]
        if wanted == original['enabled']:
            continue
        path = Path(original['path'])
        current = json.loads(path.read_text('utf-8-sig'), object_pairs_hook=_pairs)
        expected = {k:v for k,v in original.items() if k != 'path'}
        if validate_module(current, validate_config, base) != expected:
            raise ValueError(path.name+' changed on disk. Refresh the rules list before saving.')
        updated = dict(current, enabled=wanted)
        validate_module(updated, validate_config, base)
        updates.append((path, current, updated))
    done = []
    try:
        for path, old, new in updates:
            write_atomic(path, new)
            done.append((path, old))
    except OSError:
        for path, old in reversed(done):
            write_atomic(path, old)
        raise
    return len(updates)
