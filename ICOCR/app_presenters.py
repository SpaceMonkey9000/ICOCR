"""Text for the video overlay label; pure functions, no UI toolkit."""

EXACT_COLOUR = '#65f2c0'
UNCERTAIN_COLOUR = '#ffd37a'
LABEL_DESCRIPTION_LIMIT = 180


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
