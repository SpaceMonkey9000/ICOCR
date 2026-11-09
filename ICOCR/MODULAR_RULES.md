# Modular rules in ICOCR 0.8.9.2

## Use

1. Launch ICOCR with your existing shared DATA folder selected.
2. Open Settings → Rules. The list groups rules by purpose, with a checkbox per module. Search filters names, categories and IDs.
3. Save changes, then restart ICOCR. Scans continue using the startup snapshot until restart.
4. Use Open rules folder to edit or add JSON files. Refresh shows their validation results and discards unsaved checkbox changes. Restart applies the saved files.

No new dependencies are required. The normal Windows launcher/setup scripts still apply.

## What moved

| Modules | Contents |
| --- | --- |
| Device families | Each existing strict syntax, spaced-name join, broad syntax, hint and contextual correction-cost rule becomes its own module. Original precedence is retained through priority. |
| Part-number prefixes | Existing literal prefix list. |
| Metadata exclusions | Existing country/origin phrases and exact excluded words. |
| Brands | Existing manufacturer/logo words used in line ranking. |
| OCR corrections | Existing confusion pairs, costs, suffix mappings and edit limits as one coherent module. |
| Logic aliases | Existing bounded 74-series abbreviation and suffix rules. |
| Line ranking | Existing learned/contextual ranking settings and weights as one coherent module. |
| Matching and joining | Existing affix suggestions, numeric-family suggestions, literal suffix evidence, printed-family evidence, wrapped lines, same-line fragments and leading-logo removal. |
| Context, exclusions and orientation | Existing block support, lot/date penalty, short-block penalty, block preference, numeric-value/repeated-character/PCB-reference exclusions and reading-direction support. Orientation thresholds also live in its module. |
| Short MOSFET markings | New explicit prefix-candidate module, including optional single trailing hyphen handling. |

There are 56 modules with the stock configuration. Existing custom family patterns can change that count. Closely related lists are grouped so their internal constraints remain consistent; the checkbox controls that complete rule group. General OCR processing, confidence thresholds, geometry checks and identity-consistency safeguards remain part of the processing pipeline. Scalar performance/selection tuning remains in the existing tuning configuration.

Disabling one rule does not disable independent rules that can also support the same marking. For example, a literal part with a letter suffix can be supported by the general suffix rule even when the dedicated 74-series alias module is off.

## Location and migration

The active folder is `DATA/rules`, under the shared DATA location already used by ICOCR and ICDB. There is no hardcoded Windows drive. `ICOCR_RULES_DIR` can override the folder for isolated tests/tools.

At first launch, the existing validated per-user configuration seeds the modules. Missing/invalid legacy settings use the existing fallback behavior. Existing modules are never overwritten. `migration.json` marks migration completion. Do not delete it to restore defaults: doing so can repopulate intentionally removed modules.

After migration, edit DATA modules rather than the old per-user rule files. A deleted module stays absent. An invalid module is skipped and shown as an error; its legacy/default rule is not silently enabled. Keep DATA/rules when moving to another ICOCR installation. No databases or pinouts are modified.

Adding rules is supported by the existing module kinds below. A new kind of processing operation still needs application code; this system does not execute Python supplied from DATA.

## Common fields

Every module is a JSON object with `schema_version: 1`, a unique `id`, readable `name`, `category`, boolean `enabled`, and `kind`. Optional integer `priority` defaults to 100; smaller numbers run earlier, with IDs breaking ties. Stock patterns retain their original order.

Files are read from the top level of DATA/rules. Duplicate JSON keys, duplicate module IDs, duplicate configuration targets, or duplicate family IDs are reported. All modules involved in a duplicate are skipped. Unknown fields/kinds or unsupported schema versions are rejected. Each file is limited to 1 MiB.

The effective module set, enabled states, errors and hash are recorded in configuration diagnostics and scan results. Applied transformations retain their rule ID and observed text. Exact database matches retain precedence.

## Add a missing-prefix rule

Copy the stock `mosfet.short_marking.json`, give it a new ID/name and edit the parameters. Example:

```json
{
  "schema_version": 1,
  "id": "custom.mosfet_markings",
  "name": "Additional shortened MOSFET markings",
  "category": "Matching",
  "enabled": true,
  "kind": "prefix_candidates",
  "priority": 100,
  "pattern": "[0-9]{2,3}[NP][0-9]{2,3}",
  "prefixes": ["XYZ"],
  "suffixes": ["", "L"],
  "ignore_trailing_hyphen": true
}
```

This produces exact lookup names such as `XYZ50N06` and `XYZ50N06L`. Only names already in the database become candidates. Overlapping prefix modules contribute candidates together. They never establish a confirmed identity or authorize an automatic pinout from a guessed prefix. A single trailing hyphen is ignored only for this lookup, not removed from the displayed raw OCR text. No fuzzy correction is chained onto these candidates.

Patterns use bounded character classes, digits/letters, and quantifiers. Groups, alternatives, wildcards, and backreferences are not supported for this module kind. Prefixes are 1–8 uppercase letters; suffixes are 0–4 uppercase letters. At most 64 of each are allowed. Keep electrically significant suffixes distinct: the list generates possible full names, not equivalence claims.

## Add a family syntax/hint rule

```json
{
  "schema_version": 1,
  "id": "custom.zxa_syntax",
  "name": "ZXA device naming pattern",
  "category": "Device families",
  "enabled": true,
  "kind": "family",
  "priority": 100,
  "collection": "strict_patterns",
  "rule": {
    "id": "zxa",
    "label": "ZXA naming pattern",
    "pattern": "ZXA\\d{3}"
  }
}
```

Collections: `strict_patterns`, `spaced_patterns`, `broad_patterns`, `hint_patterns`, `contextual_costs`. The payload retains the existing family schema; `enabled` is controlled at module level. Strict/hint rules require a label. Contextual cost rules use `prefix_pattern`, `to_char`, and `cost` instead of `pattern`. Broad patterns use non-capturing regex groups only. Patterns establish syntax, never component identity.

## Existing configuration and built-in operation modules

### Wrapped part-number lines

`join.wrapped.json` uses kind `wrapped_join`. Edit `patterns` in the active
`DATA/rules` folder, then restart ICOCR. Each pair contains `first` and `second`
full-line patterns in reading order, and boolean `exact_only`:

```json
"patterns": [
  {"first": "[A-Z]{2,8}[0-9]{1,6}", "second": "[0-9]{1,4}[A-Z]{1,4}", "exact_only": false},
  {"first": "[A-Z]{2,8}", "second": "[0-9]{3,6}", "exact_only": true}
]
```

The first pair preserves wraps such as `ADM34` / `83ARZ`. The second supports
`TPS` / `65150` only when the concatenated name has an exact database match.
`exact_only: false` retains the existing exact-or-unique-printed-base checks;
it does not authorize arbitrary partial matches or inferred missing characters.
Geometry, orientation and conflict checks still apply. Original readings are
retained; no additional OCR passes are introduced.

There must be 1–32 pairs. Patterns accept uppercase letters/digits, character
classes such as `[A-Z]`, and finite repeats such as `{3}` or `{1,6}` (at most 32).
Groups, alternation, wildcards, escapes and unbounded repeats are rejected.
Each input token is limited to 32 characters. The checkbox controls the entire
module; the JSON controls the accepted line shapes.

Existing switch-only `join.wrapped` files load the bundled pattern defaults
without being overwritten, preserving their enabled state. Replace an old
switch-only file with the new factory module to edit its patterns explicitly.
Saving a changed checkbox also writes the expanded module. Invalid new modules
are skipped and reported, rather than falling back to defaults.

`config` modules have a supported `target` and a `config` payload using the existing validated file format. The supported targets are part prefixes, negative words, brands, OCR confusions, marking aliases and ranking/line_weights. One module owns each target. The top-level module checkbox is authoritative for enable/disable. Edit the payload for detailed tuning; preserve its required fields.

`switch` modules enable named built-in matching/context/exclusion operations. Their IDs identify the implemented operation and cannot be invented to add new behavior. `orientation` owns the reading-direction operation, `min_score` and `max_score_gap` (both 0–1). Keep its ID `orientation.pattern`.

Saving checkboxes preserves the payloads. Writes use temporary files plus replacement, and reject modules changed externally since the list was refreshed. Errors are shown in the Rules page. Refresh before editing again after an external change.

## Additional database rules

See the 0.8.9.2 entry in CHANGELOG.md for the five new modules and additive migration behavior.
