"""Validated startup-only rules. No GUI, OCR or third-party dependencies.

Set ICOCR_CONFIG_DIR before importing any ICOCR modules to select another
config directory. Missing files use defaults; invalid entries recover locally.
No files are created or modified by this loader. Restart to apply edits.
"""
import copy
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
from config_defaults import DEFAULTS

SCHEMA_VERSION = 1
from user_paths import CONFIG_DIR, SETTINGS_FILE
MAX_FILE_BYTES = 1024 * 1024
_LOG = logging.getLogger(__name__)


class ConfigError(ValueError):
    pass


def _check(ok, field, reason):
    if not ok:
        raise ConfigError(f'{field}: {reason}')


def _object(value, field, required, optional=()):
    _check(isinstance(value, dict), field, 'expected object')
    _check(not (set(required) - value.keys()), field,
           'missing keys: ' + ', '.join(sorted(set(required) - value.keys())))
    unknown = value.keys() - set(required) - set(optional)
    _check(not unknown, field, 'unknown keys: ' + ', '.join(sorted(unknown)))


def _number(value, field, low, high, integer=False):
    _check(type(value) in ((int,) if integer else (int, float)) and
           math.isfinite(value) and low <= value <= high, field,
           f'expected {"integer" if integer else "finite number"} in [{low}, {high}]')


def _strings(value, field, pattern, max_length=128):
    _check(isinstance(value, list) and len(value) <= 4096, field, 'expected list, at most 4096 entries')
    for i, word in enumerate(value):
        _check(isinstance(word, str) and 0 < len(word) <= max_length and
               re.fullmatch(pattern, word) is not None, f'{field}[{i}]', 'invalid text')
    _check(len(set(value)) == len(value), field, 'duplicate entries')


def _regex(value, field):
    _check(isinstance(value, str) and 0 < len(value) <= 2048, field, 'expected regex string, 1–2048 characters')
    try:
        pattern = re.compile(r'(?:' + value + ')')
    except re.error as exc:
        raise ConfigError(f'{field}: invalid regex: {exc}') from exc
    _check(pattern.fullmatch('') is None, field, 'must not match empty text')
    return pattern


def validate(name, data):
    """Return a normalized independent copy, or raise ConfigError."""
    _check(name in DEFAULTS, 'file', 'unknown configuration file')
    data = copy.deepcopy(data)
    template = DEFAULTS[name]
    required = set(template) - {'_note', 'fitted_on', 'cross_validation'}
    _object(data, name, required, {'_note', 'fitted_on', 'cross_validation'} & set(template))
    _check(type(data['schema_version']) is int and data['schema_version'] == SCHEMA_VERSION,
           'schema_version', f'expected {SCHEMA_VERSION}')
    if '_note' in data:
        _check(isinstance(data['_note'], str), '_note', 'expected text')
    if name == 'tuning.json':
        from tuning_schema import SPEC
        _object(data['settings'], 'settings', SPEC)
        for key, value in data['settings'].items():
            spec = SPEC[key]
            _number(value, key, spec['min'], spec['max'], integer=type(spec['default']) is int)
        from tuning_schema import range_pairs
        for low, high in range_pairs():
            _check(data['settings'][low] <= data['settings'][high], high,
                   f'must not be below {low} ({data["settings"][high]} < {data["settings"][low]})')
    elif name == 'rules/marking_aliases.json':
        for key in ('enabled', 'abbreviations'):
            _check(type(data[key]) is bool, key, 'expected boolean')
        _strings(data['families'], 'families', r'HC|HCT|AC|ACT|AHC|AHCT|LS|ALS|LVC', 4)
        _strings(data['suffixes'], 'suffixes', r'[A-Z]{1,3}', 3)
    elif name == 'logic_diagrams.json':
        _check(isinstance(data['folder'], str) and bool(data['folder']), 'folder', 'expected path')
        _check(isinstance(data['devices'], dict) and len(data['devices']) <= 4096, 'devices', 'expected mapping, maximum 4096 entries')
        for device, row in data['devices'].items():
            _strings([device], 'device', r'[A-Z0-9-]{3,40}', 40)
            _object(row, device, {'image', 'orientation', 'package', 'source', 'verified'})
            _check(row['verified'] is True, device, 'mapping must be verified')
            for key in ('image','orientation','package','source'):
                _check(isinstance(row[key],str) and 0 < len(row[key]) <= 2048, device+'.'+key, 'expected nonempty text')
            _check(Path(row['image']).suffix.lower() in ('.jpg','.jpeg') and not Path(row['image']).is_absolute() and '..' not in Path(row['image']).parts, device+'.image', 'expected relative JPG path inside diagram folder')
            _check(row['orientation'] == 'top view', device+'.orientation', 'expected top view')
    elif name == 'rules/part_prefixes.json':
        _strings(data['prefixes'], 'prefixes', r'[A-Za-z0-9-]+', 24)
        data['prefixes'] = [x.upper() for x in data['prefixes']]
        _check(len(set(data['prefixes'])) == len(data['prefixes']), 'prefixes', 'case-insensitive duplicates')
    elif name == 'rules/negative_words.json':
        for key in ('origin_words', 'origin_phrases', 'extra_exact'):
            _strings(data[key], key, r'[A-Za-z0-9]+(?: [A-Za-z0-9]+)*')
            data[key] = [x.upper() for x in data[key]]
            _check(len(set(data[key])) == len(data[key]), key, 'case-insensitive duplicates')
        _check(all(' ' not in x for x in data['origin_words']), 'origin_words', 'expected single words')
    elif name == 'rules/device_families.json':
        for key in ('strict_patterns', 'spaced_patterns', 'broad_patterns', 'hint_patterns', 'contextual_costs'):
            entries = data[key]
            _check(isinstance(entries, list) and len(entries) <= 512, key, 'expected list, at most 512 rules')
            ids = set()
            for i, row in enumerate(entries):
                field = f'{key}[{i}]'
                fields = {'id', 'enabled'} | ({'prefix_pattern', 'to_char', 'cost'} if key == 'contextual_costs' else {'pattern'})
                if key in ('strict_patterns', 'hint_patterns'):
                    fields.add('label')
                _object(row, field, fields)
                _strings([row['id']], field+'.id', r'[A-Za-z0-9_-]+', 64)
                _check(row['id'] not in ids, field+'.id', 'duplicate rule ID')
                ids.add(row['id'])
                _check(type(row['enabled']) is bool, field+'.enabled', 'expected boolean')
                pattern_key = 'prefix_pattern' if key == 'contextual_costs' else 'pattern'
                compiled = _regex(row[pattern_key], field+'.'+pattern_key)
                if key == 'broad_patterns':
                    _check(compiled.groups == 0, field+'.pattern', 'use non-capturing groups (?:...) in broad patterns')
                if 'label' in row:
                    _check(isinstance(row['label'], str) and 0 < len(row['label']) <= 160, field+'.label', 'expected nonempty text')
                if key == 'contextual_costs':
                    _strings([row['to_char']], field+'.to_char', r'[A-Z0-9]', 1)
                    _number(row['cost'], field+'.cost', 0, 10)
        for key in ('orientation_min_score', 'orientation_max_score_gap'):
            _number(data[key], key, 0, 1)
    elif name == 'rules/ocr_confusions.json':
        _check(isinstance(data['pairs'], list) and len(data['pairs']) <= 630, 'pairs', 'expected list, at most 630 pairs')
        pairs = set()
        for i, row in enumerate(data['pairs']):
            field = f'pairs[{i}]'
            _object(row, field, {'chars', 'cost'})
            _strings([row['chars']], field+'.chars', r'[A-Z0-9]{2}', 2)
            pair = frozenset(row['chars'])
            _check(len(pair) == 2 and pair not in pairs, field+'.chars', 'self-pair or duplicate bidirectional pair')
            pairs.add(pair)
            _number(row['cost'], field+'.cost', 0, 10)
        _check(isinstance(data['suffix_letters'], dict), 'suffix_letters', 'expected object')
        for a, b in data['suffix_letters'].items():
            _strings([a], 'suffix_letters key', r'[0-9]', 1)
            _strings([b], 'suffix_letters value', r'[A-Z]', 1)
            _check(frozenset((a, b)) in pairs, 'suffix_letters', f'{a}/{b} requires a listed confusion pair')
        _number(data['max_suffix'], 'max_suffix', 0, 3, integer=True)
        limits = data['edit_limits']
        _check(isinstance(limits, list) and 1 <= len(limits) <= 24, 'edit_limits', 'expected 1–24 length bands')
        previous = 0
        for i, row in enumerate(limits):
            _object(row, f'edit_limits[{i}]', {'max_length', 'max_edits'})
            _number(row['max_length'], 'max_length', previous + 1, 24, integer=True)
            _number(row['max_edits'], 'max_edits', 0, min(3, row['max_length']), integer=True)
            previous = row['max_length']
        _check(previous == 24, 'edit_limits', 'last max_length must be 24')
        for key in ('base_max_cost', 'extra_edit_cost'):
            _number(data[key], key, 0, 10)
    elif name == 'rules/brands.json':
        _check(isinstance(data['brands'], dict) and len(data['brands']) <= 4096, 'brands', 'expected object, at most 4096 manufacturers')
        for brand, words in data['brands'].items():
            _check(bool(brand.strip()), 'brands', 'empty manufacturer')
            _strings(words, f'brands.{brand}', r'[A-Za-z0-9]+')
            data['brands'][brand] = [w.upper() for w in words]
    elif name == 'ranking/line_weights.json':
        _check(type(data['enabled']) is bool, 'enabled', 'expected boolean')
        _number(data['extended_min_score'], 'extended_min_score', 0, 1)
        _check(data['line_ranking_version'] == template['line_ranking_version'], 'line_ranking_version', 'unsupported feature model')
        _check(isinstance(data['version'], str) and bool(data['version']), 'version', 'expected nonempty text')
        _object(data['weights'], 'weights', template['weights'])
        for key, value in data['weights'].items():
            _number(value, 'weights.'+key, -100, 100)
        _number(data['bias'], 'bias', -100, 100)
        if data['abstain_below'] is not None:
            _number(data['abstain_below'], 'abstain_below', -1000, 1000)
        for key in ('fitted_on', 'cross_validation'):
            if key in data:
                _check(isinstance(data[key], dict), key, 'expected object')
    return data


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConfigError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def _canonical(data):
    return json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def _effective(data):
    """Exclude descriptive/training metadata from the behaviour hash."""
    return {k: v for k, v in data.items() if k not in ('_note', 'fitted_on', 'cross_validation', 'version')}


def recover_entries(name, data):
    """In-memory migration; preserve disk bytes and valid sibling settings."""
    if not isinstance(data, dict):
        raise ConfigError('expected object')
    data = copy.deepcopy(data)
    issues = []
    version = data.get('schema_version', 1)
    _check(type(version) is int and version == 1, 'schema_version', 'unsupported version')
    data.setdefault('schema_version', 1)
    default = DEFAULTS[name]
    for key, value in default.items():
        if key not in data:
            data[key] = copy.deepcopy(value)
            issues.append(key + ': missing; migrated default')
    # Existing file schemas remain v1; configuration set v2 adds files/settings.
    # Validate independently at the smallest safe unit; collections with
    # relational constraints (confusion pairs, family regex groups) stay atomic.
    for key in list(data):
        if key not in default:
            data.pop(key)
            issues.append(key + ': unknown; ignored')
    if name == 'tuning.json' and isinstance(data.get('settings'), dict):
        from tuning_schema import SPEC
        supplied = data['settings']
        clean = {}
        for key, spec in SPEC.items():
            value = supplied.get(key, spec['default'])
            try:
                _number(value, key, spec['min'], spec['max'], integer=type(spec['default']) is int)
            except ConfigError as exc:
                issues.append(str(exc) + '; default active')
                value = spec['default']
            clean[key] = value
        from tuning_schema import range_pairs
        for low, high in range_pairs():
            if clean[high] < clean[low]:
                issues.append(f'{high}: {clean[high]} is below {low} ({clean[low]}); '
                              f'defaults active for both')
                clean[low], clean[high] = SPEC[low]['default'], SPEC[high]['default']
        issues.extend(key + ': unknown; ignored' for key in supplied if key not in SPEC)
        data['settings'] = clean
    if name == 'ranking/line_weights.json' and isinstance(data.get('weights'), dict):
        weights = copy.deepcopy(default['weights'])
        for key, value in data['weights'].items():
            try:
                _check(key in weights, 'weights.'+key, 'unknown weight')
                _number(value, 'weights.'+key, -100, 100)
                weights[key] = value
            except ConfigError as exc:
                issues.append(str(exc) + '; default active')
        data['weights'] = weights
    try:
        validate(name, data)
        return data, issues
    except ConfigError:
        pass
    clean = copy.deepcopy(default)
    for key, value in data.items():
        probe = copy.deepcopy(clean)
        probe[key] = value
        try:
            validate(name, probe)
            clean = probe
        except ConfigError as exc:
            issues.append(str(exc) + '; default active for ' + key)
    return clean, issues


class ConfigSnapshot:
    """Independent startup snapshot; no disk reads after construction."""
    def __init__(self, directory=CONFIG_DIR):
        self.directory = Path(directory).expanduser().resolve()
        self._data = {}
        files = {}
        warnings = []
        for name, default in DEFAULTS.items():
            # Rules are loaded exclusively from DATA/rules; only application-only
            # configuration sections come from the single settings.json.
            section = {'tuning.json': 'tuning', 'logic_diagrams.json': 'logic_diagrams'}.get(name)
            path = self.directory / "settings.json" if section else self.directory / name
            status, issue = 'external', ''
            try:
                if section:
                    with path.open('rb') as handle:
                        raw = handle.read(MAX_FILE_BYTES + 1)
                    container = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_no_duplicates)
                    if not isinstance(container, dict) or container.get('schema_version') != 1:
                        raise ConfigError('invalid application settings schema')
                    data = container[section]
                    raw = _canonical(data).encode('utf-8')
                else:
                    # Rules use internal validation defaults only until the
                    # modular RuleSnapshot replaces them.
                    data = default
                    raw = _canonical(data).encode('utf-8')
                if len(raw) > MAX_FILE_BYTES:
                    raise ConfigError('file exceeds 1 MiB')
                data = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_no_duplicates,
                                  parse_constant=lambda value: (_ for _ in ()).throw(ConfigError('non-finite JSON number: '+value)))
                data, entry_issues = recover_entries(name, data)
                if entry_issues:
                    status, issue = 'partial_default', '; '.join(entry_issues)
                data = validate(name, data)
                # Also reject non-finite metadata and unreasonable nesting.
                _canonical(data)
            except FileNotFoundError:
                status, issue = 'missing_default', 'file missing; bundled defaults active'
                data = validate(name, default)
            except (OSError, UnicodeError, ValueError, TypeError, RecursionError, OverflowError) as exc:
                status, issue = 'invalid_default', f'{exc}; bundled defaults active'
                data = validate(name, default)
            self._data[name] = data
            files[name] = dict(status=status, sha256=hashlib.sha256(_canonical(_effective(data)).encode()).hexdigest())
            if issue:
                files[name]['warning'] = issue
                warning = f'{path}: {issue}'
                warnings.append(warning)
                _LOG.warning('%s', warning)
        self._report = dict(schema_version=SCHEMA_VERSION, directory=str(self.directory),
                            sha256=hashlib.sha256(_canonical({n:_effective(v) for n,v in self._data.items()}).encode()).hexdigest(),
                            files=files, warnings=warnings, restart_required=True, configuration_version=2, active_configuration=copy.deepcopy(self._data))

    def get(self, name):
        return copy.deepcopy(self._data[name])

    def diagnostics(self):
        return copy.deepcopy(self._report)


CONFIG = ConfigSnapshot()
_LEGACY_DATA = copy.deepcopy(CONFIG._data)
from rule_modules import RuleSnapshot, rules_directory


def _activate_rules():
    global RULES
    RULES = RuleSnapshot(rules_directory(), _LEGACY_DATA, validate)
    CONFIG._data = copy.deepcopy(RULES.config)
    CONFIG._report['active_configuration'] = copy.deepcopy(CONFIG._data)
    CONFIG._report['sha256'] = hashlib.sha256(_canonical(CONFIG._data).encode()).hexdigest()
    CONFIG._report['modular_rules'] = dict(directory=str(RULES.directory), sha256=RULES.sha256,
        modules=[{k:v for k,v in row.items() if k != 'path'} for row in RULES.modules], errors=RULES.errors)
    legacy_warnings = CONFIG._report['warnings']
    CONFIG._report['warnings'] = legacy_warnings + [error['file']+': '+error['error'] for error in RULES.errors]
    from rule_modules import GROUPS, FAMILY_FILE
    for name in ((*GROUPS, FAMILY_FILE) if RULES.directory.exists() else ()):
        CONFIG._report['files'][name] = dict(status='modular_rules',
            sha256=hashlib.sha256(_canonical(_effective(CONFIG._data[name])).encode()).hexdigest())


def initialize_rules():
    # Called by prepare_config before OCR/matching modules capture their snapshot.
    _activate_rules()
    _DIAGNOSTICS_CACHE.clear()


def rule_enabled(rule_id):
    return RULES.enabled(rule_id)


_activate_rules()


def get_config(name):
    return CONFIG.get(name)


_RUNTIME_OVERRIDE_KEYS = ('ICOCR_LINE_RANKING', 'ICOCR_BODY_MIN_FRACTION', 'ICOCR_DEFER_BODY_RETRY',
                          'ICOCR_TARGETED_ORIGINAL', 'ICOCR_STRAIGHTEN_FALLBACK', 'ICOCR_DETECTOR_ALIGNMENT',
                          'ICLENS_DEVICE', 'ICOCR_CUDNN_SEARCH')
_DIAGNOSTICS_CACHE = {}


def configuration_diagnostics():
    """Startup configuration report, attached to every scan result.

    The configuration is startup-only, so the report (deep copy + hashes) is
    built once per (snapshot, runtime-override environment) and cached. Each
    call returns a new top-level dict; nested values are shared with the cache
    and must be treated as read-only (copy before modifying).
    """
    overrides = tuple((key, os.environ[key]) for key in _RUNTIME_OVERRIDE_KEYS if key in os.environ)
    cache_key = (CONFIG, overrides)
    report = _DIAGNOSTICS_CACHE.get(cache_key)
    if report is None:
        report = CONFIG.diagnostics()
        # Preserve the existing environment override used by tests/benchmark tools.
        override = os.environ.get('ICOCR_LINE_RANKING')
        enabled = override != '0' if override is not None else CONFIG._data['ranking/line_weights.json']['enabled']
        report['line_ranking_enabled'] = enabled
        report['runtime_overrides'] = dict(overrides)
        report['effective_sha256'] = hashlib.sha256(_canonical(dict(
            config_sha256=report['sha256'], rules_sha256=report['modular_rules']['sha256'], line_ranking_enabled=enabled, runtime_overrides=report['runtime_overrides'])).encode()).hexdigest()
        if len(_DIAGNOSTICS_CACHE) > 16:
            _DIAGNOSTICS_CACHE.clear()
        _DIAGNOSTICS_CACHE[cache_key] = report
    return dict(report)


def tuning(key):
    """Startup-only scalar lookup shared by the app and benchmark imports."""
    return CONFIG._data['tuning.json']['settings'][key]
