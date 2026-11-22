"""Captured case 015 plus database and syntax priority regressions."""
import os
from pathlib import Path
import json
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('ICOCR_RULES_DIR',str(ROOT/'factory'/'rules'))
sys.path.insert(0,str(ROOT))
from component_catalog import Catalog
from scan_result import build_scan_result
from marking_rules import weak_prefix_hint

class WeakPrefixTests(unittest.TestCase):
    def setUp(self):
        self.rows=json.loads(Path(__file__).with_name('weak_prefix_case015.json').read_text())
        self.catalog=Catalog.__new__(Catalog);self.catalog.records={}
    def test_015_selects_correct_printed_marking_without_identity_guess(self):
        result=build_scan_result(self.rows,self.rows,self.catalog)
        self.assertEqual(result['selected_marking'],'VP1050')
        self.assertEqual(result['resolved_partnumber'],'')
        weak=next(r for r in result['all_candidates'] if r['key']=='SI4BT')
        self.assertTrue(weak['weak_prefix_hint'])
        self.assertEqual(weak['line_features']['family_pattern'],0)
    def test_exact_database_match_still_wins(self):
        self.catalog.records={'SI4BT':[dict(part='SI4BT',manufacturer='',family='',source='fixture',line=1,
            package='',qualifiers='',component_function='fixture',entry_function='fixture')]}
        result=build_scan_result(self.rows,self.rows,self.catalog)
        self.assertEqual(result['selected_marking'],'SI4BT')
        self.assertEqual(result['resolved_partnumber'],'SI4BT')
    def test_strict_syntax_and_numeric_structure_stay_strong(self):
        for key in ('LM339','74HC14D','SI2302','BQ24075'):
            self.assertFalse(weak_prefix_hint(key),key)
        self.assertTrue(weak_prefix_hint('SI4BT'))
    def test_weak_hint_is_not_a_hard_exclusion(self):
        rows=[r for r in self.rows if r['key']=='SI4BT']
        result=build_scan_result(rows,rows,self.catalog)
        self.assertEqual(result['selected_marking'],'SI4BT')
        self.assertFalse(result['selected']['exclusion_reason'])
if __name__=='__main__':unittest.main(verbosity=2)
