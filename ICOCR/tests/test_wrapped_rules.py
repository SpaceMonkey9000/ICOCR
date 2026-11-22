"""Offline wrapped-line rule and resolver regressions; no camera or OCR models."""
import copy
import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import component_catalog as catalog_module
from config_defaults import DEFAULTS
from config_loader import validate
from rule_modules import RuleSnapshot, save_enabled, validate_module, wrapped_defaults


class Catalog:
    def __init__(self, part, match_type='exact'):
        self.part, self.match_type = part, match_type
        self.calls = []

    def find(self, key):
        self.calls.append(key)
        return [dict(part=self.part, match_type=self.match_type)]


def row(key, y, x=0, rotation=0):
    return dict(key=key, text=key, box=[[x,y],[x+100,y],[x+100,y+20],[x,y+20]],
                score=.99, rank=1, rotation=rotation)


class WrappedRules(unittest.TestCase):
    def join(self, rows, catalog, rule=None):
        rule = validate_module(rule or wrapped_defaults(), validate, DEFAULTS)
        patterns = tuple((re.compile(p['first']), re.compile(p['second']), p['exact_only'])
                         for p in rule['patterns'])
        limits = {'component_catalog.wrapped_height_min':.5,
                  'component_catalog.wrapped_vertical_min':.6,
                  'component_catalog.wrapped_horizontal_ratio':.6,
                  'component_catalog.wrapped_rank_bonus':.15,
                  'marking_context.neighbour_alignment_cosine':.94}
        with patch.object(catalog_module, 'WRAPPED_PATTERNS', patterns), \
             patch.object(catalog_module, 'rule_enabled', return_value=rule['enabled']), \
             patch.object(catalog_module, 'tuning', side_effect=limits.__getitem__):
            return catalog_module.joined_markings(rows, catalog)

    def test_prefix_numeric_exact_join_preserves_sources(self):
        rows = [row('TPS',0), row('65150',30)]
        original = copy.deepcopy(rows)
        result = self.join(rows, Catalog('TPS65150'))
        self.assertEqual([r['key'] for r in result], ['TPS65150'])
        self.assertEqual(result[0]['observed_markings'], ['TPS','65150'])
        self.assertEqual(result[0]['joined_from'], ['TPS','65150'])
        self.assertEqual(rows, original)

    def test_legacy_wrap_and_printed_suffix_still_work(self):
        for part, match in [('ADM3483ARZ','exact'), ('ADM3483','partial')]:
            self.assertEqual(self.join([row('ADM34',0),row('83ARZ',30)],
                                      Catalog(part,match))[0]['key'], 'ADM3483ARZ')

    def test_numeric_join_rejects_partial_or_inferred_identity(self):
        for part, match in [('TPS6515','partial'), ('TPS65150','rule_candidate')]:
            self.assertEqual(self.join([row('TPS',0),row('65150',30)], Catalog(part,match)), [])

    def test_geometry_orientation_and_conflicts_still_gate_joins(self):
        reverse = row('65150',30,rotation=180)
        reverse['box'] = reverse['box'][2:] + reverse['box'][:2]
        variants = [row('65150',300), row('65150',30,x=300),
                    reverse, dict(row('65150',30),conflicts=['6515O'])]
        for second in variants:
            with self.subTest(second=second):
                self.assertEqual(self.join([row('TPS',0),second],Catalog('TPS65150')), [])

    def test_retained_same_pass_views_join_despite_representative_rotations(self):
        first = dict(row('TPS',0),pass_id=5)
        second = dict(row('65150',30,rotation=180),pass_id=7)
        second['box'] = second['box'][2:] + second['box'][:2]
        first['observation_evidence'] = [dict(first)]
        second['observation_evidence'] = [dict(row('65150',30),pass_id=5),dict(second)]
        result = self.join([first,second],Catalog('TPS65150'))
        self.assertEqual(result[0]['key'],'TPS65150')
        self.assertEqual([v['pass_id'] for v in result[0]['join_evidence']],[5,5])

    def test_different_passes_cannot_supply_a_join(self):
        self.assertEqual(self.join([dict(row('TPS',0),pass_id=5),
                                    dict(row('65150',30),pass_id=7)],Catalog('TPS65150')),[])

    def test_rotation_labels_do_not_override_physical_alignment(self):
        result = self.join([row('TPS',0),row('65150',30,rotation=90)],Catalog('TPS65150'))
        self.assertEqual(result[0]['key'],'TPS65150')

    @unittest.skipUnless(importlib.util.find_spec('cv2'), 'OpenCV needed for complete selection pipeline')
    def test_actual_image_geometry_through_complete_selection(self):
        from ocr_core import split_candidates
        from scan_result import build_scan_result
        # Retained observations from the supplied image, cropped to its chip.
        first = dict(row('TPS',0),pass_id=5,score=.9866868655,mode='Original',
                     box=[[101.3093,151.1732],[169.8168,102.5654],[190.0700,131.1101],[121.5625,179.7180]])
        second = dict(row('65150',0,rotation=180),pass_id=7,score=.9993972898,mode='Original',
                      box=[[249.3520,132.5761],[153.1153,200.8586],[134.5980,174.7605],[230.8347,106.4780]])
        shared = dict(row('65150',0),pass_id=5,score=.9993225813,mode='Original',
                      box=[[135.4136,174.1818],[232.0056,103.8080],[251.7987,130.8401],[155.2066,201.2139]])
        catalog = catalog_module.Catalog.__new__(catalog_module.Catalog)
        catalog.records = {'TPS65150': [dict(part='TPS65150',manufacturer='TI',family='',
            source='test',line='',package='QFN',qualifiers='',component_function='',entry_function='')]}
        rows, _, every = split_candidates([first,second,shared],modes=1)
        self.assertNotEqual(next(r['rotation'] for r in every if r['key']=='TPS'),
                            next(r['rotation'] for r in every if r['key']=='65150'))
        result = build_scan_result(rows,every,catalog)
        self.assertEqual(result['selected_marking'],'TPS65150')
        self.assertEqual(result['resolved_partnumber'],'TPS65150')
        self.assertEqual(next(r['selection_decision'] for r in result['all_candidates']
                              if r['key']=='TPS'),'rejected')
        self.assertEqual([v['pass_id'] for v in result['selected']['join_evidence']],[5,5])

    def test_disabled_rule_and_numeric_date_after_complete_part(self):
        disabled = dict(wrapped_defaults(), enabled=False)
        self.assertEqual(self.join([row('TPS',0),row('65150',30)],Catalog('TPS65150'),disabled), [])
        self.assertEqual(self.join([row('TPS65150',0),row('2345',30)],Catalog('TPS651502345')), [])

    def test_json_edit_changes_accepted_shapes(self):
        custom = dict(wrapped_defaults(), patterns=[dict(first='ZX',second='[0-9]{4}',exact_only=True)])
        self.assertEqual(self.join([row('ZX',0),row('1234',30)],Catalog('ZX1234'),custom)[0]['key'], 'ZX1234')
        self.assertEqual(self.join([row('TPS',0),row('65150',30)],Catalog('TPS65150'),custom), [])

    def test_invalid_rule_payloads_are_rejected(self):
        bad_pairs = [dict(first='(A+)+',second='[0-9]{3}',exact_only=True),
                     dict(first='[Z-A]',second='[0-9]{3}',exact_only=True),
                     dict(first='[A-Z]{0}',second='[0-9]{3}',exact_only=True),
                     dict(first='[A-Z]{8,2}',second='[0-9]{3}',exact_only=True),
                     dict(first='TPS',second='[0-9]{3}',exact_only=1)]
        for pair in bad_pairs:
            with self.subTest(pair=pair), self.assertRaises(ValueError):
                validate_module(dict(wrapped_defaults(),patterns=[pair]),validate,DEFAULTS)
        for value in ([], {}, [dict(first='TPS',second='[0-9]{3}')]):
            with self.assertRaises(ValueError):
                validate_module(dict(wrapped_defaults(),patterns=value),validate,DEFAULTS)

    def test_factory_snapshot_validates_and_activates_rule(self):
        snapshot = RuleSnapshot(ROOT/'factory'/'rules',DEFAULTS,validate)
        self.assertEqual(snapshot.errors, [])
        self.assertTrue(snapshot.enabled('join.wrapped'))

    def test_legacy_switch_load_and_checkbox_save(self):
        legacy = {k:v for k,v in wrapped_defaults().items() if k != 'patterns'}
        legacy['kind'] = 'switch'
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'join.wrapped.json'
            path.write_text(json.dumps(legacy))
            snapshot = RuleSnapshot(td,DEFAULTS,validate)
            self.assertEqual(snapshot.errors, [])
            self.assertEqual(snapshot.modules[0]['patterns'],wrapped_defaults()['patterns'])
            self.assertEqual(json.loads(path.read_text()),legacy)
            self.assertEqual(save_enabled(snapshot.modules,{'join.wrapped':False},validate,DEFAULTS),1)
            saved = json.loads(path.read_text())
            self.assertEqual(saved['kind'],'wrapped_join')
            self.assertEqual(saved['patterns'],wrapped_defaults()['patterns'])
            self.assertFalse(RuleSnapshot(td,DEFAULTS,validate).enabled('join.wrapped'))

    def test_invalid_installed_module_does_not_fall_back(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td)/'join.wrapped.json').write_text(json.dumps(dict(wrapped_defaults(),patterns=[])))
            snapshot = RuleSnapshot(td,DEFAULTS,validate)
            self.assertEqual(len(snapshot.errors),1)
            self.assertFalse(snapshot.enabled('join.wrapped'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
