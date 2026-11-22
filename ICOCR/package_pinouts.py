"""Read-only package taxonomy and bounded pinout selection for coarse classifiers."""
import json
import logging
import math
import re

from project_paths import ROOT
from user_paths import CONFIG_DIR

GROUPS = frozenset(('SOP', 'QF', 'TO'))
_cached = None
_signature = None


def key(value):
    return re.sub(r'[^A-Z0-9]', '', str(value or '').upper())


def configuration():
    global _cached, _signature
    user = CONFIG_DIR/'package_groups.json'
    path = user if user.is_file() else ROOT/'factory'/'package_groups.json'
    try:
        stamp = (str(path), path.stat().st_mtime_ns, path.stat().st_size)
        if stamp != _signature:
            data = json.loads(path.read_text(encoding='utf-8'))
            if data.get('version') != 1 or set(data.get('groups', {})) != GROUPS:
                raise ValueError('Expected SOP, QF and TO package groups, version 1')
            for name in ('minimum_confidence', 'minimum_margin'):
                value = data[name]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
                    raise ValueError('Invalid '+name)
            for group in GROUPS:
                families = data['groups'][group]['families']
                if not isinstance(families, list) or any(not isinstance(f, str) or not key(f) for f in families):
                    raise ValueError('Invalid package family list')
            overrides = data.get('overrides', {})
            if not isinstance(overrides, dict) or any(v not in GROUPS and v is not None for v in overrides.values()):
                raise ValueError('Invalid package overrides')
            _cached, _signature = data, stamp
        return _cached
    except Exception as exc:
        logging.warning('Package grouping unavailable: %s', exc)
        return None


def package_groups(value, config=None):
    """Whole-name families with bounded suffixes; never substring guessing."""
    config = configuration() if config is None else config
    if config is None:
        return frozenset()
    normalized = key(value)
    overrides = {key(k): v for k, v in config.get('overrides', {}).items()}
    if normalized in overrides:
        return frozenset((overrides[normalized],)) if overrides[normalized] else frozenset()
    groups = set()
    # Shared references can explicitly name more than one package, e.g. SOIC-8 / DIP-8.
    for atom in re.split(r'[,;/|+]', str(value or '')):
        atom = key(atom)
        if not atom:
            continue
        found = set()
        for group, spec in config['groups'].items():
            for family in spec['families']:
                if re.fullmatch(re.escape(key(family))+r'(?:[0-9]{1,3}[A-Z]{0,4})?', atom):
                    found.add(group)
        if not found:
            return frozenset()  # partly unknown declarations are not automatic evidence
        groups.update(found)
    return frozenset(groups)


def detected_group(result, config=None):
    config = configuration() if config is None else config
    if not config or not result or result.get('status') != 'classified':
        return None
    group = result.get('package')
    if group not in GROUPS:
        return None
    try:
        score = float(result['confidence'])
        scores = {c['package']: float(c['confidence']) for c in result.get('candidates', [])}
        if (set(scores) != GROUPS or not all(math.isfinite(v) and 0 <= v <= 1 for v in scores.values())
                or not math.isclose(sum(scores.values()), 1., abs_tol=1e-4)
                or not math.isclose(scores[group], score, abs_tol=1e-5)):
            return None
        runner_up = max(v for k, v in scores.items() if k != group)
        return group if score >= config['minimum_confidence'] and score-runner_up >= config['minimum_margin'] else None
    except (KeyError, TypeError, ValueError):
        return None


def select_reference(choices, package='', remembered=None, prediction=None, config=None):
    """Return (entry or None, serializable decision). All choices stay in the UI."""
    config = configuration() if config is None else config
    group = detected_group(prediction, config)
    report = dict(group=group, automatic=False, reason='', compatible=[], manual=False)
    manual = next((e for e in choices if remembered is not None and e.get('reference_id') == remembered), None)
    if manual is not None:
        report.update(manual=True, reason='Manual reference selection' + ('; detected '+group if group else ''))
        return manual, report
    if not group:
        # No usable visual evidence: preserve the pre-classifier selection behavior.
        exact = [e for e in choices if package and key(e.get('package')) == key(package)]
        pool = exact or choices
        entry = next((e for e in pool if e.get('is_default')), pool[0] if pool else None)
        report.update(reason='No reliable package group; database reference selection', automatic=entry is not None)
        return entry, report
    pool = [e for e in choices if group in package_groups(e.get('package'), config)]
    report['compatible'] = [e.get('reference_id') for e in pool]
    if not pool:
        report['reason'] = 'Detected '+group+'; no compatible linked pinout — select a reference'
        return None, report
    exact = [e for e in pool if package and key(e.get('package')) == key(package)]
    candidates = exact or pool
    default = next((e for e in candidates if e.get('is_default')), None)
    entry = default or candidates[0]
    reason = ('exact database package' if exact else
              'default compatible reference' if default is not None else 'first compatible reference')
    report.update(automatic=True, reason='Detected '+group+'; '+reason,
                  compatible_count=len(pool), remaining_options=len(candidates),
                  pin_count_inferred=False)
    return entry, report


def with_package(row, diagnostics):
    """Attach context to a presentation copy; OCR/database rows stay unchanged."""
    if row is None:
        return None
    return dict(row, package_classification=(diagnostics or {}).get('package_classification'))


def compatible_corrected_aliases(suggestions, prediction):
    """Use coarse package evidence only to rule out known conflicting families."""
    group = detected_group(prediction)
    if group is None:
        return list(suggestions)
    compatible = []
    for match in suggestions:
        packages = [package_groups(p) for p in match.get('alias_packages', ())]
        if not packages or not all(packages) or any(group in groups for groups in packages):
            compatible.append(match)
    return compatible


def corrected_alias_label(match):
    corrected = match['correction']['corrected_text']
    device = match['part']
    maker = match.get('manufacturer') or 'Manufacturer unspecified'
    packages = ', '.join(match.get('alias_packages', ()))
    return f'{corrected} → {device} · {maker}' + (f' ({packages})' if packages else '')
