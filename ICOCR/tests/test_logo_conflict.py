"""Case 028 replay plus protections against real conflicting identities."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import component_catalog as cc
from scan_result import build_scan_result

class LogoConflictTests(unittest.TestCase):
    def setUp(self):
        self.rows=json.loads(Path(__file__).with_name('logo_conflict_case028.json').read_text())
        self.catalog=cc.Catalog.__new__(cc.Catalog)
        self.catalog.records={}
        self.add('HEF4538B')
    def add(self, name):
        self.catalog.records[name]=[dict(part=name, manufacturer='',family='',source='fixture',line=1,
            package='',qualifiers='',component_function='Dual monostable',entry_function='Dual monostable')]
    def winner(self,rows=None):
        return next(r for r in cc.annotate(rows or self.rows,self.catalog) if r['key']=='HEF4538BT')
    def test_case028_complete_selection_and_trace(self):
        result=build_scan_result(self.rows,self.rows,self.catalog)
        self.assertEqual(result['selected_marking'],'HEF4538BT')
        self.assertEqual(result['resolved_partnumber'],'HEF4538B')
        selected=result['selected']
        self.assertEqual(selected['conflicts'],['TLHEF4538BT'])
        self.assertEqual(selected['logo_prefix_conflicts'][0]['rule_id'],'conflict.leading_TL_logo')
    def test_different_database_identity_still_blocks(self):
        self.add('TLHEF4538BT')
        self.assertFalse(self.winner()['database_identity_consistent'])
    def test_numeric_conflict_still_blocks(self):
        target=next(r for r in self.rows if r['key']=='HEF4538BT')
        target['conflicts'].append('HEF4539BT')
        self.assertFalse(self.winner()['database_identity_consistent'])
    def test_unknown_prefix_still_blocks(self):
        for row in self.rows:
            if row['key']=='TLHEF4538BT': row['key']=row['text']='ZZHEF4538BT'
            if row['key']=='HEF4538BT': row['conflicts']=['ZZHEF4538BT']
        self.assertFalse(self.winner()['database_identity_consistent'])
    def test_missing_or_distant_geometry_still_blocks(self):
        for box in (None, [[10000,10000],[10100,10000],[10100,10020],[10000,10020]]):
            rows=copy.deepcopy(self.rows)
            next(r for r in rows if r['key']=='TLHEF4538BT')['box']=box
            self.assertFalse(self.winner(rows)['database_identity_consistent'])
    def test_disabled_logo_rule_preserves_conflict(self):
        original=cc.rule_enabled
        with patch.object(cc,'rule_enabled',side_effect=lambda k:False if k=='join.logo' else original(k)):
            self.assertFalse(self.winner()['database_identity_consistent'])

if __name__=='__main__':unittest.main(verbosity=2)
