"""Regression: components created in ICDB without source entries must match in ICOCR."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from component_catalog import Catalog

class ManualComponentCatalogTest(unittest.TestCase):
    def test_manual_component_and_source_backed_component(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'components.sqlite'
            with sqlite3.connect(path) as db:
                db.executescript('''
                  CREATE TABLE components(id INTEGER PRIMARY KEY, part_number TEXT,
                      manufacturer TEXT, family_hint TEXT, function TEXT);
                  CREATE TABLE sources(id INTEGER PRIMARY KEY, name TEXT);
                  CREATE TABLE entries(id INTEGER PRIMARY KEY, component_id INTEGER,
                      source_id INTEGER, status TEXT, line INTEGER,
                      package_or_interface TEXT, qualifiers TEXT, function TEXT);
                  INSERT INTO components VALUES(1,'MANUAL123','', '', 'Manually created controller');
                  INSERT INTO components VALUES(2,'SOURCE456','TI','', 'Imported part');
                  INSERT INTO components VALUES(3,'OTHER789','', '', 'Other status only');
                  INSERT INTO sources VALUES(1,'Manufacturer catalogue');
                  INSERT INTO entries VALUES(1,2,1,'source_listed',12,'SOIC-8','','');
                  INSERT INTO entries VALUES(2,3,1,'unverified',23,'','','');
                ''')
            catalog = Catalog(path)
            self.assertEqual(catalog.count, 3)
            manual = catalog.find('MANUAL123')
            self.assertEqual(len(manual), 1)
            self.assertEqual(manual[0]['component_function'], 'Manually created controller')
            self.assertEqual(manual[0]['source'], 'ICDB manual')
            imported = catalog.find('SOURCE456')
            self.assertEqual(len(imported), 1)
            self.assertEqual(imported[0]['source'], 'Manufacturer catalogue')
            self.assertEqual(imported[0]['package'], 'SOIC-8')
            self.assertEqual(len(catalog.find('OTHER789')), 1)
            # The cache must not drop manually added components on reopening.
            self.assertEqual(Catalog(path).count, 3)

if __name__ == '__main__':
    unittest.main()
