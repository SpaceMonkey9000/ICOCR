"""Prefix token retention and suffix joins; no OCR model required."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import component_catalog as cc
from ocr_core import line_tokens, split_candidates
from scan_result import build_scan_result

def token(text,y,x=0):
    rows=line_tokens(text,.99,0,'Original',[[x,y],[x+100,y],[x+100,y+20],[x,y+20]])
    for r in rows:r['pass_id']=1
    return rows

class ShortPrefixJoin(unittest.TestCase):
    def setUp(self):
        self.catalog=cc.Catalog.__new__(cc.Catalog)
        self.catalog.records={'LM2903':[dict(part='LM2903',manufacturer='',family='',source='fixture',line=1,
           package='',qualifiers='',component_function='Comparator',entry_function='Comparator')]}
    def run_rows(self,raw):
        rows,_,all_rows=split_candidates(raw,modes=1)
        return build_scan_result(rows,all_rows,self.catalog)
    def test_retains_prefix_but_does_not_select_it_alone(self):
        raw=token('LM',0)
        self.assertEqual(raw[0]['key'],'LM')
        rows,_,all_rows=split_candidates(raw,modes=1)
        self.assertEqual(rows,[])
        self.assertTrue(all_rows[0]['join_only'])
        self.assertEqual(self.run_rows(raw)['selected_marking'],'')
    def test_lm_suffix_full_pipeline(self):
        r=self.run_rows(token('LM',0)+token('2903M',30))
        self.assertEqual(r['selected_marking'],'LM2903M')
        self.assertEqual(r['resolved_partnumber'],'LM2903')
        self.assertEqual(r['selected']['joined_from'],['LM','2903M'])
    def test_unknown_two_letter_tokens_stay_filtered(self):
        from ocr_core import _PREFIXES
        for key in ('ZZ','ON','TI','ST'):
            if key in _PREFIXES:
                self.assertEqual(self.run_rows(token(key,0))['selected_marking'],'')
            else:
                self.assertEqual(token(key,0),[])
    def test_no_geometry_or_database_guess(self):
        for second in (token('2903M',300),token('2903M',30,500),token('2904M',30)):
            self.assertNotEqual(self.run_rows(token('LM',0)+second)['selected_marking'],'LM2903M')
    def test_conflict_or_different_pass_blocks_join(self):
        raw=token('LM',0)+token('2903M',30)
        raw[-1]['pass_id']=2
        self.assertNotEqual(self.run_rows(raw)['selected_marking'],'LM2903M')
    def test_disabled_join_rule(self):
        original=cc.rule_enabled
        with patch.object(cc,'rule_enabled',side_effect=lambda k:False if k=='join.wrapped' else original(k)):
            self.assertNotEqual(self.run_rows(token('LM',0)+token('2903M',30))['selected_marking'],'LM2903M')
if __name__=='__main__':unittest.main(verbosity=2)
