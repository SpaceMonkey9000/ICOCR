"""Regressions against retained observations from ICBENCH 2026-11-12."""
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from component_catalog import Catalog, logic_marking_derivatives, annotate, live_candidates

class LogicReconstruction(unittest.TestCase):
    def setUp(self):
        self.rows=json.loads(Path(__file__).with_name('logic_reconstruction_cases.json').read_text())
        self.catalog=Catalog.__new__(Catalog)
        self.catalog.records={p:[dict(part=p,match_type='exact',component_function='fixture',entry_function='fixture')]
                              for p in ('74HC14','74HCT273','74AHC00','LM78L05','LM78L12')}
    def test_recorded_geometry_and_database_resolution(self):
        for n,key,base in [('10','HC14A','74HC14'),('12','HCT273A','74HCT273'),('46','AHC00','74AHC00')]:
            with self.subTest(case=n):
                rows=annotate(self.rows[n],self.catalog)
                derived=next(r for r in rows if r['key']==key)
                self.assertEqual(derived['resolved_partnumber'],base)
                self.assertIn(key,[r['key'] for r in live_candidates(rows,self.catalog,annotated=True)])
    def test_missing_database_does_not_infer_identity(self):
        self.catalog.records={}
        for n in ('10','12','46'):
            self.assertEqual(logic_marking_derivatives(self.rows[n],self.catalog),[])
    def test_incomplete_regulator_is_withheld(self):
        rows=annotate(self.rows['29'],self.catalog)
        self.assertNotIn('LM78L',[r['key'] for r in live_candidates(rows,self.catalog,annotated=True)])
    def test_unrelated_lines_do_not_join(self):
        import copy
        rows=copy.deepcopy(self.rows['12'])
        for row in rows:
            if row['key']=='273A':
                row['box']=[[x+5000,y] for x,y in row['box']]
                for v in row.get('observation_evidence',[]):
                    v['box']=[[x+5000,y] for x,y in v['box']]
        self.assertEqual(logic_marking_derivatives(rows,self.catalog),[])
if __name__=='__main__':unittest.main(verbosity=2)
