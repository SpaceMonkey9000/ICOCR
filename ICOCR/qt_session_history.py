"""In-memory session history of accepted readings, de-duplicated by marking."""
from copy import deepcopy
from time import strftime


def match_quality(row):
    matches = row.get('trusted_database_matches') or []
    return 2 if any(m.get('match_type') == 'exact' for m in matches) else int(bool(matches))


class ReadingHistory:
    def __init__(self):
        self.entries = []
        self.indices = {}

    def add(self, rows, database_loaded):
        changed = False
        for row in rows:
            key = str(row.get('text') or row.get('key') or '').strip().upper()
            if not key:
                continue
            if key in self.indices:
                entry = self.entries[self.indices[key]]
                if entry.get('manually_selected'):
                    continue  # the technician's choice is never replaced by a scan
                if match_quality(row) > match_quality(entry['row']):
                    entry.update(row=deepcopy(row), database_loaded=database_loaded)
                    changed = True
                continue
            self.indices[key] = len(self.entries)
            self.entries.append(dict(row=deepcopy(row), time=strftime('%H:%M:%S'),
                                     database_loaded=database_loaded))
            changed = True
        return changed

    def add_selected(self, row, database_loaded):
        """Explicit technician selection wins over a previous automatic entry."""
        key = str(row.get('text') or row.get('key') or '').strip().upper()
        if not key:
            return False
        chosen = deepcopy(row)
        chosen['manually_selected'] = True
        if key in self.indices:
            self.entries[self.indices[key]].update(
                row=chosen, database_loaded=database_loaded,
                manually_selected=True)
        else:
            self.indices[key] = len(self.entries)
            self.entries.append(dict(
                row=chosen, time=strftime('%H:%M:%S'),
                database_loaded=database_loaded, manually_selected=True))
        return True

    def clear(self):
        self.entries.clear()
        self.indices.clear()
