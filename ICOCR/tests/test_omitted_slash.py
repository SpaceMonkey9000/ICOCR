"""Regression for OCR dropping slash separators in long IC markings."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from component_catalog import Catalog, annotate


class OmittedSlashTest(unittest.TestCase):
    def make_catalog(self, parts, aliases=()):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / 'test.sqlite'
        with sqlite3.connect(path) as db:
            db.executescript('''
                CREATE TABLE components(id INTEGER PRIMARY KEY, part_number TEXT,
                    manufacturer TEXT, family_hint TEXT, function TEXT);
                CREATE TABLE entries(id INTEGER PRIMARY KEY, component_id INTEGER,
                    source_id INTEGER, status TEXT, line INTEGER,
                    package_or_interface TEXT, qualifiers TEXT, function TEXT);
                CREATE TABLE sources(id INTEGER PRIMARY KEY, name TEXT);
                CREATE TABLE component_marking_aliases(component_id INTEGER,
                    marking TEXT, packages_json TEXT, source TEXT);
            ''')
            for i, part in enumerate(parts, 1):
                db.execute('INSERT INTO components VALUES(?,?,?,?,?)', (i, part, 'NXP', '', ''))
            for component_id, marking in aliases:
                db.execute('INSERT INTO component_marking_aliases VALUES(?,?,?,?)',
                           (component_id, marking, '[]', 'datasheet'))
        return Catalog(path)

    def test_part_number_missing_slashes(self):
        catalog = self.make_catalog(['TJA1055/3/C'])
        result = catalog.find('TJA10553C')
        self.assertEqual([m['part'] for m in result], ['TJA1055/3/C'])
        self.assertEqual(result[0]['match_type'], 'exact')
        rows = annotate([dict(text='TJA10553C', key='TJA10553C', score=.99)], catalog)
        self.assertEqual(rows[0]['resolved_partnumber'], 'TJA1055/3/C')

    def test_marking_alias_missing_slashes(self):
        catalog = self.make_catalog(['TJA1055'], [(1, 'TJA1055/3/C')])
        self.assertEqual(catalog.explicit_marking_matches('TJA10553C')[0]['part'], 'TJA1055')

    def test_ambiguous_collapsed_markings_do_not_match(self):
        catalog = self.make_catalog(['TJA1055/3/C', 'TJA105/53C'])
        self.assertFalse(catalog._omitted_slash_matches('TJA10553C'))

    def test_short_codes_and_hyphens_not_broadened(self):
        catalog = self.make_catalog(['A/2', 'TJA-1055/3/C'])
        self.assertFalse(catalog._omitted_slash_matches('A2'))
        self.assertFalse(catalog._omitted_slash_matches('TJA10553C'))


if __name__ == '__main__':
    unittest.main()
