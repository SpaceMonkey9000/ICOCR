"""Display references from the shared DATA/components.sqlite database only."""
from icdb_references import ReferenceIndex, package_key
from project_paths import DATA


class DiagramLibrary:
    def __init__(self, data_folder=None, background=True):
        from pathlib import Path
        self.folder = Path(data_folder or DATA)
        from shared_data import database_file
        self.references = ReferenceIndex(database_file(self.folder))
        self.reason = 'No pinout linked in ICDB'
        if background:self.references.start()
        else:self.references.poll()

    def choices(self, row):
        if not row or row.get('provisional') or row.get('rejection_reason'):return []
        match = row.get('selected_database_match')
        if not match:return []
        choices, reason = self.references.choices(match)
        if match.get('alias_packages'):
            allowed = {package_key(value) for value in match['alias_packages']}
            choices = [choice for choice in choices if package_key(choice.get('package')) in allowed]
        self.reason = reason or ('No pinout linked in ICDB' if not choices else '')
        if not choices and 'unavailable' in self.references.status:
            self.reason = self.references.status
        return choices

    def lookup(self, row):
        choices = self.choices(row)
        match = (row or {}).get('selected_database_match') or {}
        return default_reference(choices, match.get('package',''), prediction=(row or {}).get('package_classification'))

    def close(self):self.references.close()
    def refresh(self):self.references.refresh()
    @property
    def generation(self):return self.references.generation
    @property
    def status(self):return self.references.status


def default_reference(choices, package='', remembered=None, prediction=None):
    from package_pinouts import select_reference
    return select_reference(choices, package, remembered, prediction)[0]


def reference_labels(choices):
    labels = []
    for entry in choices:
        label = entry.get('package') or 'General reference'
        from package_pinouts import package_groups
        groups = package_groups(entry.get('package'))
        label += ' [' + ' / '.join(sorted(groups)) + ']' if groups else ' [unmapped]'
        if entry.get('pin_count'):label += f" · {entry['pin_count']} pins"
        if entry.get('label'):label += ' — '+entry['label']
        if entry.get('is_default'):label += ' (default)'
        labels.append(label)
    duplicates = {label for label in labels if labels.count(label)>1}
    return [label+' — '+e['path'].name+' ['+e['reference_id']+']' if label in duplicates else label
            for label,e in zip(labels,choices)]
