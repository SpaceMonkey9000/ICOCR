"""Identify a truncated live reading using the previous reading of its body."""
from body_locator import overlap_fraction
from confusion_matching import COST
from ocr_core import normalize


def previous_full_reading(row, previous_rows):
    if not row or row.get('selected_database_match') or not row.get('body_box') or not row.get('box'):
        return None
    prefix = normalize(row['key'])
    if len(prefix) < 5:
        return None
    matches = []
    for previous in previous_rows:
        body = previous.get('body_box')
        marking = previous.get('box')
        match = previous.get('selected_database_match')
        if not body or not marking or not match:
            continue
        words = {normalize(previous['key']), normalize(match['part'])}
        for word in words:
            if not 1 <= len(word) - len(prefix) <= 3:
                continue
            edits = [(a, b) for a, b in zip(prefix, word) if a != b]
            if len(edits) <= 1 and all(edit in COST for edit in edits):
                break
        else:
            continue
        current_body = row['body_box']
        if (overlap_fraction(current_body, body) >= .80 and overlap_fraction(body, current_body) >= .80
                and overlap_fraction(row['box'], marking) >= .60):
            matches.append(previous)
    return matches[0] if len(matches) == 1 else None
