"""Regressions for the review fixes: DATA folder and captures, ICDB hand-off arguments,
History keeping manual choices, and the shared OCR engine."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class DataFolderTests(unittest.TestCase):
    def run_isolated(self, script, env):
        result = subprocess.run([sys.executable, '-c', script], cwd=ROOT, text=True,
                                capture_output=True, timeout=30, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_data_follows_shared_resolution(self):
        with tempfile.TemporaryDirectory() as td:
            data = Path(td) / 'Shared' / 'DATA'
            env = dict(os.environ, ICLENS_DATA=str(data), LOCALAPPDATA=str(Path(td) / 'home'))
            env.pop('ICOCR_RULES_DIR', None)
            found = self.run_isolated(
                'import json; from project_paths import DATA; from rule_modules import rules_directory;'
                'print(json.dumps([str(DATA), str(rules_directory())]))', env)
            self.assertEqual(found, [str(data.resolve()), str((data / 'rules').resolve())])

    def test_launcher_does_not_force_folders(self):
        source = (ROOT / 'qt_full.py').read_text('utf-8')
        for name in ('ICLENS_DATA', 'ICOCR_RULES_DIR', 'ICOCR_CONFIG_DIR', 'prototype-config'):
            self.assertNotIn(f"os.environ['{name}']", source)
        self.assertNotIn('prototype-config', source)

    def test_default_captures_go_to_pictures(self):
        from user_paths import default_capture_directory
        captures = default_capture_directory()
        self.assertEqual(captures.name, 'ICOCR')
        self.assertNotEqual(captures.parent.name, 'DATA')
        if os.name != 'nt':
            self.assertEqual(captures, Path.home() / 'Pictures' / 'ICOCR')


class BridgeTests(unittest.TestCase):
    def launch(self, action, part, target=None):
        from qt_icdb_bridge import launch_icdb
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'icdb_qt.py').write_text("'--open-part' '--add-part' '--add-alias'")
            (folder / 'run_qt_windows.bat').write_text('')
            calls = []
            with patch('qt_icdb_bridge.os.name', 'posix'):
                launch_icdb(folder, folder / 'DATA', part, action=action, target=target,
                            popen=lambda argv, **kw: calls.append(argv))
            return calls[0][2:]

    def parse(self, argv):
        # The same declarations as ICDB's icdb_qt.main().
        parser = argparse.ArgumentParser()
        for option in ('--data', '--open-part', '--add-part', '--add-alias'):
            parser.add_argument(option)
        parser.add_argument('--alias-part', default='')
        parser.add_argument('--alias-manufacturer', default='')
        return parser.parse_args(argv)

    def test_values_starting_with_a_hyphen_reach_icdb(self):
        self.assertEqual(self.parse(self.launch('open', '-5V')).open_part, '-5V')
        self.assertEqual(self.parse(self.launch('add', '--weird')).add_part, '--weird')
        args = self.parse(self.launch('alias', '-ABC', dict(part='-P', manufacturer='M')))
        self.assertEqual((args.add_alias, args.alias_part, args.alias_manufacturer), ('-ABC', '-P', 'M'))


class HistoryTests(unittest.TestCase):
    def test_scan_never_replaces_manual_choice(self):
        from qt_session_history import ReadingHistory
        history = ReadingHistory()
        history.add_selected(dict(key='ABC', selected_database_match=dict(part='CHOSEN'),
                                  trusted_database_matches=[]), True)
        changed = history.add([dict(key='ABC', selected_database_match=dict(part='AUTO'),
                                    trusted_database_matches=[dict(match_type='exact', part='AUTO')])], True)
        self.assertFalse(changed)
        self.assertEqual(history.entries[0]['row']['selected_database_match']['part'], 'CHOSEN')

    def test_unchanged_scan_reports_no_change(self):
        from qt_session_history import ReadingHistory
        history = ReadingHistory()
        row = dict(key='ABC', trusted_database_matches=[])
        self.assertTrue(history.add([row], True))
        self.assertFalse(history.add([row], True))


class EngineTests(unittest.TestCase):
    def setUp(self):
        # A private copy of ui/workers.py: other tests replace ui.workers.shared_ocr
        # with a stub for the whole session.
        import importlib.util
        spec = importlib.util.spec_from_file_location('ui_workers_under_test', ROOT / 'ui' / 'workers.py')
        self.workers = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.workers)

    def test_failed_engine_is_not_rebuilt_until_retry(self):
        attempts = []

        def broken():
            attempts.append(1)
            raise OSError('model missing')
        self.workers.OCR = broken
        for _ in range(3):
            with self.assertRaises(Exception):
                self.workers.shared_ocr()
        self.assertEqual(len(attempts), 1)
        self.assertTrue(self.workers.engine_failed())
        self.workers.retry_engine()
        with self.assertRaises(OSError):
            self.workers.shared_ocr()
        self.assertEqual(len(attempts), 2)

    def test_warm_up_and_scan_do_not_overlap(self):
        active, overlap = [], []

        class Engine:
            runtime = {'label': 'stub'}
            last_diagnostics = {}

            def warm_up(self):
                active.append(1)
                time.sleep(.2)
                active.pop()

        self.workers._ENGINE = Engine()
        loader = threading.Thread(target=self.workers.EngineLoader.run, args=(_Signals(),))
        loader.start()
        time.sleep(.05)
        started = time.monotonic()
        with self.workers.ENGINE_IN_USE:          # what a scan holds
            overlap.append(bool(active))
        loader.join()
        self.assertEqual(overlap, [False])
        self.assertGreater(time.monotonic() - started, .1)


class _Signals:
    """Stands in for EngineLoader's Qt signals."""
    class _Signal:
        def emit(self, *args):
            pass
    loaded = failed = _Signal()


if __name__ == '__main__':
    unittest.main(verbosity=2)
