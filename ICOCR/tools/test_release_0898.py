"""Offline integration checks for 0.8.9.8. Does not require Tk, camera or ONNX runtime."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FACTORY = ROOT/'factory'/'rules'

def run_isolated(script, home, data):
    env = dict(os.environ, LOCALAPPDATA=str(home), ICOCR_CONFIG_DIR=str(home/'ICSuite'/'ICOCR'), ICLENS_DATA=str(data))
    env.pop('ICOCR_RULES_DIR', None)
    p = subprocess.run([sys.executable, '-c', script], cwd=ROOT, env=env, text=True, capture_output=True, timeout=25)
    if p.returncode:
        raise AssertionError(f'{p.stdout}\n{p.stderr}')
    return json.loads(p.stdout)

class ReleaseIntegration(unittest.TestCase):
    def test_clean_install_preserves_updates_and_models(self):
        with tempfile.TemporaryDirectory() as td:
            home, data = Path(td)/'home', Path(td)/'DATA'
            result = run_isolated('''
import json
from user_paths import prepare_config, SETTINGS_FILE
from project_paths import DATA
prepare_config(DATA)
from config_loader import initialize_rules, configuration_diagnostics
initialize_rules()
r=configuration_diagnostics()
print(json.dumps({'errors':r['modular_rules']['errors'],'modules':len(r['modular_rules']['modules']),'settings':SETTINGS_FILE.is_file()}))
''', home, data)
            self.assertEqual(result['errors'], [])
            self.assertEqual(result['modules'], len(list(FACTORY.glob('*.json'))))
            self.assertTrue(result['settings'])
            rules = list((data/'rules').glob('*.json'))
            self.assertEqual(len(rules), len(list(FACTORY.glob('*.json'))))
            sample = rules[0]
            sample.write_text(sample.read_text()+'\n',encoding='utf-8')
            original = hashlib.sha256(sample.read_bytes()).digest()
            settings = home/'ICSuite'/'ICOCR'/'settings.json'
            values=json.loads(settings.read_text());values['ui']['sleep_seconds']=93
            settings.write_text(json.dumps(values))
            result = run_isolated('''
import json
from user_paths import prepare_config, SETTINGS_FILE
from project_paths import DATA
prepare_config(DATA)
from config_loader import initialize_rules,configuration_diagnostics
initialize_rules()
print(json.dumps({'seconds':json.loads(SETTINGS_FILE.read_text())['ui']['sleep_seconds'],'errors':configuration_diagnostics()['modular_rules']['errors']}))
''',home,data)
            self.assertEqual(result['seconds'],93)
            self.assertEqual(result['errors'],[])
            self.assertEqual(hashlib.sha256(sample.read_bytes()).digest(),original)
            self.assertFalse((home/'ICSuite'/'ICOCR'/'config').exists())

    def test_rule_edit_and_validation(self):
        with tempfile.TemporaryDirectory() as td:
            home,data=Path(td)/'home',Path(td)/'DATA'
            run_isolated('from user_paths import prepare_config; from project_paths import DATA; prepare_config(DATA); print("{}")',home,data)
            path=data/'rules'/'ranking.lines.json'
            row=json.loads(path.read_text());row['enabled']=False
            path.write_text(json.dumps(row))
            report=run_isolated('''
import json
from config_loader import configuration_diagnostics
r=configuration_diagnostics()
print(json.dumps({'enabled':r['line_ranking_enabled'],'errors':r['modular_rules']['errors']}))
''',home,data)
            self.assertFalse(report['enabled'])
            self.assertEqual(report['errors'],[])
            path.write_text('{ invalid json')
            report=run_isolated('''
import json
from config_loader import configuration_diagnostics
r=configuration_diagnostics()
print(json.dumps({'errors':r['modular_rules']['errors']}))
''',home,data)
            self.assertEqual(len(report['errors']),1)
            self.assertIn('ranking.lines.json',report['errors'][0]['file'])

    def test_body_model_metadata_is_bundled(self):
        data=ROOT.parent/'DATA'/'models'
        self.assertTrue((data/'ic_body_segment.onnx').is_file())
        self.assertTrue((data/'ic_body_segment.json').is_file())
        self.assertGreater((data/'ic_body_segment.onnx').stat().st_size,100000)
        json.loads((data/'ic_body_segment.json').read_text())

if __name__=='__main__':
    unittest.main(verbosity=2)
