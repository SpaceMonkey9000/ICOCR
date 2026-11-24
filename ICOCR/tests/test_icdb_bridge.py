import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from qt_icdb_bridge import icdb_entry, launch_icdb

class BridgeTests(unittest.TestCase):
    def test_missing_app_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                icdb_entry(tmp)
    def test_argv_and_data_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'icdb_qt.py').write_text("parser.add_argument('--open-part')")
            (root/'run_qt_windows.bat').write_text('')
            popens = []
            with patch('qt_icdb_bridge.os.name', 'posix'):
                launch_icdb(root, root/'DATA', 'TPS65150', popen=lambda *a, **kw: popens.append((a,kw)))
            args, options = popens[0]
            self.assertEqual(args[0][-2:], [f"--data={(root/'DATA').resolve()}", '--open-part=TPS65150'])
            self.assertEqual(options['cwd'], str(root))
    def test_windows_uses_python_not_cmd(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ['icdb_qt.py','run_qt_windows.bat']:
                (root/name).write_text("parser.add_argument('--open-part')" if name == 'icdb_qt.py' else '')
            winpython = root/'.venv-qt'/'Scripts'/'python.exe'
            winpython.parent.mkdir(parents=True)
            winpython.touch()
            calls = []
            with patch('qt_icdb_bridge.os', type('FakeOS', (), {'name': 'nt'})()):
                launch_icdb(root, root/'DATA', 'A&B', popen=lambda *a, **kw: calls.append((a,kw)))
            self.assertEqual(calls[0][0][0][0],str(winpython))
            self.assertEqual(calls[0][0][0][-1],'--open-part=A&B')

if __name__ == '__main__':
    unittest.main()
