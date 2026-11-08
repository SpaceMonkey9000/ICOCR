"""Tk-free text for the status panel, video overlay label and logged rows (0.8.4.8).

These were inline in the controller's Tk methods; as pure functions they are
unit-testable without a display. Wording is unchanged from 0.8.4.7.
"""
from component_catalog import functions

EXACT_COLOUR = '#65f2c0'
UNCERTAIN_COLOUR = '#ffd37a'
LABEL_DESCRIPTION_LIMIT = 180
PROCESSORS = {'cuda': 'CUDA', 'cpu': 'CPU'}


def runtime_text(runtime, elapsed):
    """(footer text, OCR processor line or '') for an OCR runtime description."""
    footer = f"{PROCESSORS.get(runtime.get('device'), '—')} | {elapsed:.2f} s"
    label = ''
    if runtime.get('label'):
        label = 'OCR processor: ' + runtime['label'] + (' — '+runtime['reason'] if runtime.get('reason') else '')
    return footer, label


def match_kind(row, chosen, matches):
    if chosen and chosen.get('match_type') == 'abbreviated':
        return 'Abbreviated marking'
    if chosen and chosen.get('match_type') == 'family_suffix':
        return 'Package suffix'
    if row.get('ocr_correction'):
        return 'Corrected OCR'
    if any(m.get('match_type') == 'rule_candidate' for m in matches):
        return 'Rule suggestion'
    if any(m.get('match_type') == 'partial' for m in matches):
        return 'Partial'
    return 'Exact'


def candidate_overlay(row):
    """Status line shown at the top of the video for a selected reading."""
    if not row.get('database_matches'):
        return row['key'] + ' • unverified candidate'
    if row.get('selected_database_match'):
        return row['key'] + ' • ' + row['function_summary'] + ' • unverified match'
    return row['key'] + ' • database suggestions — identity unknown'


def candidate_evidence(row, saved=None):
    """Recognition evidence text (Diagnostics) for one reading.

    saved: the known-marking entry for row['key'] (DATA/matches.json or the
    bundled seed), if any.
    """
    lines = [row.get('status', ''), row.get('evidence', '')]
    if row.get('observed_markings'):
        lines.append('Observed text: ' + ' | '.join(row['observed_markings']))
    if row.get('conflicts'):
        lines.append('Conflicting text: '+', '.join(row['conflicts']))
    if saved:
        lines.append('Saved entry: '+saved['part'])
    matches = row.get('database_matches')
    if matches:
        if any(m.get('match_type') == 'rule_candidate' for m in matches):
            lines.append('Possible parts: ' + ', '.join(sorted({m['part'] for m in matches})))
        chosen = row.get('selected_database_match')
        if chosen:
            lines.append('Displayed database entry: ' + chosen['part'])
            if chosen.get('match_type') in ('abbreviated', 'family_suffix'):
                lines.append('Resolved base: ' + chosen['part'] + ' — manufacturer and package unresolved')
        if row.get('database_ambiguous'):
            lines.append('* Multiple database variants/descriptions; unresolved variants are suggestions only.')
        values = functions(matches)
        lines.append('Database function: ' + ('; '.join(values) if values else 'Function not recorded'))
        lines.append(match_kind(row, chosen, matches) + ' database name match; source-listed, unverified.')
        lines.append('Sources: '+', '.join(sorted({str(m.get('source') or 'unknown source') for m in matches})))
        lines.append('Open Database details for manufacturers and packages.')
    if row.get('family_hint'):
        lines.append(row['family_hint'])
    if row.get('correction_suggestions') and not row.get('ocr_correction'):
        names = sorted({m['part'] for m in row['correction_suggestions']})
        lines.append('OCR correction suggestions (not applied): '+', '.join(names))
    lines.append('Compare with snapshot. Neither a name match nor a family pattern confirms identity.')
    return '\n'.join(lines)


def overlay_label(row, database_loaded):
    """(label text, colour) drawn beside a tracked marking on the video."""
    matches = row.get('trusted_database_matches', [])
    exact = bool(matches) and all(m.get('match_type') == 'exact' for m in matches)
    colour = EXACT_COLOUR if exact and not row.get('database_ambiguous') else UNCERTAIN_COLOUR
    description = row.get('function_summary') or (
        'No database match' if database_loaded else 'Set up DATA database for description')
    if not matches and any(m.get('match_type') == 'rule_candidate' for m in row.get('database_matches', [])):
        description = 'Possible matches: ' + ', '.join(sorted({m['part'] for m in row['database_matches']}))
    if row.get('provisional') and not matches:
        description = 'Identity unknown — ' + description
    abbreviated = any(m.get('match_type') == 'abbreviated' for m in matches)
    if row.get('ocr_correction'):
        description = 'Corrected OCR: ' + description
    elif abbreviated:
        description = 'Abbreviated marking: ' + description
    elif any(m.get('match_type') == 'family_suffix' for m in matches):
        description = 'Package suffix: ' + description
    elif matches and not exact:
        description = 'Partial match: ' + description
    if len(description) > LABEL_DESCRIPTION_LIMIT:
        # function_summary ends with ' *' for ambiguous entries: keep it visible.
        description = description[:LABEL_DESCRIPTION_LIMIT-3] + '…'
        if row.get('database_ambiguous'):
            description += ' *'
    if row.get('ocr_correction'):
        label = row['resolved_partnumber'] + ' — corrected from ' + row['text']
    elif abbreviated:
        label = row['text'] + ' → ' + row['resolved_partnumber']
    elif row.get('vote_summary'):
        label = ('' if row.get('vote_confirmed') else 'Checking: ') + row['text'] + '  (' + row['vote_summary'] + ')'
    else:
        label = ('Provisional: ' if not matches else '') + row['text']
    return label + '\n' + description, colour


def confirmation_fields(row, automatic, lines, edited, mode, chip, scan, database):
    """Fields of one confirmed.csv row for a clicked (or edited) reading."""
    if edited:
        corrected, correction = 'yes', 'edited text'
    elif automatic is None:
        corrected, correction = 'yes', 'chosen; no automatic pick'
    elif automatic.get('key') == row.get('key'):
        corrected, correction = 'no', 'accepted automatic pick'
    else:
        corrected, correction = 'yes', 'picked another line'
    text = row.get('text') or row.get('key', '')
    part = row.get('resolved_partnumber') or (row.get('selected_database_match') or {}).get('part', '')
    return dict(part_number=part or text, confirmed_text=text,
                database_match='yes' if part else 'no',
                corrected=corrected, correction=correction,
                ocr_text=(row.get('edited_from', '') if edited else row.get('raw_text') or text),
                automatic_pick=(automatic or {}).get('text', (automatic or {}).get('key', '')),
                all_readings=' | '.join(dict.fromkeys(r.get('text') or r.get('key', '') for r in lines)),
                mode=mode, chip=chip, scan=scan, database=database)
