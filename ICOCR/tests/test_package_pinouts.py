"""Broad package groups must not turn into unsupported exact pinout guesses."""
import copy
import json
import os
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('ICOCR_RULES_DIR', str(ROOT/'factory'/'rules'))
sys.path.insert(0, str(ROOT))
from package_pinouts import package_groups, select_reference, detected_group, with_package
from logic_diagrams import default_reference, reference_labels

CONFIG = json.loads((ROOT/'factory'/'package_groups.json').read_text())


def prediction(group, confidence=.95):
    return dict(status='classified', package=group, confidence=confidence,
                candidates=[dict(package=g, confidence=confidence if g == group else (1-confidence)/2)
                            for g in ('SOP', 'QF', 'TO')])


def entry(package, pins, index, default=False, path=None):
    return dict(package=package, pin_count=pins, reference_id=str(index),
                is_default=default, path=Path(path or str(index)+'.png'), stamp=(1, 1), source='fixture', label='')


class Groups(unittest.TestCase):
    def test_two_sided(self):
        for name in ('SOIC-8', 'TSSOP-14', 'SSOP-28', 'MSOP-8', 'SOP16', 'SO-8', 'PowerSO20', 'DIP-8', 'PDIP-16'):
            with self.subTest(name=name):self.assertEqual(package_groups(name, CONFIG), {'SOP'})

    def test_four_sided(self):
        for name in ('QFP-64', 'LQFP100', 'TQFP-32', 'QFN-48', 'PLCC-52', 'LCC-20'):
            with self.subTest(name=name):self.assertEqual(package_groups(name, CONFIG), {'QF'})

    def test_power_tab(self):
        for name in ('TO-220-3', 'TO-247-3', 'TO-252-5', 'TO-263-7', 'DPAK', 'D2PAK', 'SOT-223-4', 'SOT-89-3'):
            with self.subTest(name=name):self.assertEqual(package_groups(name, CONFIG), {'TO'})

    def test_untrained_or_unknown_not_forced_into_group(self):
        for name in ('BGA-64', 'FBGA-100', 'WLCSP', 'DFN-8', 'SOT-23-6', 'SOT-323', 'SOT-563', 'TO-92', 'TO-18', 'SOFTWARE', '', None):
            with self.subTest(name=name):self.assertEqual(package_groups(name, CONFIG), set())

    def test_shared_and_partly_unknown_package_declarations(self):
        self.assertEqual(package_groups('SOIC-8 / DIP-8', CONFIG), {'SOP'})
        self.assertEqual(package_groups('SOIC-8 / QFP-32', CONFIG), {'SOP', 'QF'})
        self.assertFalse(package_groups('SOIC-8 / BGA-64', CONFIG))

    def test_explicit_alias_and_exclusion(self):
        config = copy.deepcopy(CONFIG)
        config['overrides'] = {'VendorCustom-12': 'QF', 'SOIC-8': None}
        self.assertEqual(package_groups('VendorCustom12', config), {'QF'})
        self.assertFalse(package_groups('SOIC8', config))

    def test_low_unknown_and_malformed_predictions_not_used(self):
        for p in (prediction('SOP', .7), dict(status='disabled'), dict(status='classified', package='SOP', confidence=.99)):
            self.assertIsNone(detected_group(p, CONFIG))
        p=prediction('SOP');p['candidates'][0]['confidence']=.1
        self.assertIsNone(detected_group(p, CONFIG))

    def test_visual_group_changes_reference_despite_cross_group_database_default(self):
        choices = [entry('QFP-32', 32, 1, True), entry('SOIC-8', 8, 2)]
        chosen, decision = select_reference(choices, package='QFP-32', prediction=prediction('SOP'), config=CONFIG)
        self.assertEqual(chosen['reference_id'], '2')
        self.assertEqual(decision['group'], 'SOP')
        self.assertEqual(len(choices), 2)

    def test_missing_compatible_pinout_returns_no_automatic_diagram(self):
        choices = [entry('QFP-32', 32, 1, True)]
        chosen, decision = select_reference(choices, prediction=prediction('TO'), config=CONFIG)
        self.assertIsNone(chosen)
        self.assertIn('no compatible', decision['reason'])

    def test_default_is_chosen_among_compatible_pin_counts(self):
        choices = [entry('SOIC-8', 8, 1, True), entry('SOIC-16', 16, 2)]
        self.assertEqual(select_reference(choices, prediction=prediction('SOP'), config=CONFIG)[0]['reference_id'], '1')

    def test_default_is_chosen_among_compatible_layouts(self):
        choices = [entry('DIP-8', 8, 1, True), entry('SOIC-8', 8, 2)]
        self.assertEqual(select_reference(choices, prediction=prediction('SOP'), config=CONFIG)[0]['reference_id'], '1')

    def test_exact_package_resolves_within_compatible_group(self):
        choices = [entry('SOIC-8', 8, 1, True), entry('SOIC-16', 16, 2)]
        self.assertEqual(select_reference(choices, package='SOIC16', prediction=prediction('SOP'), config=CONFIG)[0]['reference_id'], '2')

    def test_three_compatible_references_choose_default(self):
        choices=[entry('SOIC-8',8,1),entry('TSSOP-8',8,2,True),entry('DIP-8',8,3)]
        chosen,decision=select_reference(choices,prediction=prediction('SOP'),config=CONFIG)
        self.assertEqual(chosen['reference_id'],'2')
        self.assertEqual(decision['compatible_count'],3)
        self.assertFalse(decision['pin_count_inferred'])

    def test_three_compatible_references_without_default_choose_first(self):
        choices=[entry('QFP-32',32,0,True),entry('SOIC-8',8,1),entry('TSSOP-8',8,2),entry('DIP-8',8,3)]
        chosen,decision=select_reference(choices,prediction=prediction('SOP'),config=CONFIG)
        self.assertEqual(chosen['reference_id'],'1')
        self.assertEqual(decision['compatible_count'],3)

    def test_duplicate_aliases_of_same_image_and_pin_count_are_usable(self):
        choices = [entry('SOIC-8', 8, 1, path='shared.png'), entry('DIP-8', 8, 2, path='shared.png')]
        self.assertIsNotNone(select_reference(choices, prediction=prediction('SOP'), config=CONFIG)[0])
        choices[1]['pin_count']=16
        self.assertEqual(select_reference(choices, prediction=prediction('SOP'), config=CONFIG)[0]['reference_id'], '1')

    def test_no_prediction_preserves_legacy_default(self):
        choices = [entry('QFP-32', 32, 1), entry('SOIC-8', 8, 2, True)]
        self.assertEqual(default_reference(choices)['reference_id'], '2')
        self.assertEqual(default_reference(choices, package='QFP32')['reference_id'], '1')

    def test_manual_selection_overrides_group(self):
        choices = [entry('QFP-32', 32, 1), entry('SOIC-8', 8, 2)]
        chosen, decision=select_reference(choices, remembered='1', prediction=prediction('SOP'), config=CONFIG)
        self.assertEqual(chosen['reference_id'], '1')
        self.assertTrue(decision['manual'])

    def test_context_copies_row_without_affecting_database_selection(self):
        row={'selected_database_match':{'part':'TEST'},'key':'TEST'}
        copied=with_package(row, {'package_classification':prediction('TO')})
        self.assertNotIn('package_classification', row)
        self.assertIs(copied['selected_database_match'],row['selected_database_match'])

    def test_labels_expose_group_and_keep_pin_count(self):
        labels=reference_labels([entry('TSSOP-14',14,1), entry('BGA-64',64,2)])
        self.assertIn('[SOP]',labels[0]);self.assertIn('14 pins',labels[0]);self.assertIn('[unmapped]',labels[1])


    def test_first_run_seeds_mapping_and_keeps_user_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            home=Path(directory)
            env=dict(os.environ,ICOCR_CONFIG_DIR=str(home/'config'),ICLENS_DATA=str(home/'DATA'))
            env.pop('ICOCR_RULES_DIR',None)
            script='''
import json
from user_paths import prepare_config, CONFIG_DIR
prepare_config()
path=CONFIG_DIR/'package_groups.json'
data=json.loads(path.read_text())
assert set(data['groups'])=={'SOP','QF','TO'}
data['minimum_confidence']=.91
path.write_text(json.dumps(data))
prepare_config()
assert json.loads(path.read_text())['minimum_confidence']==.91
'''
            result=subprocess.run([sys.executable,'-c',script],cwd=ROOT,env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)








if __name__=='__main__':unittest.main()
