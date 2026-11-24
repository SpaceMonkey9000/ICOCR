"""CLI handoff for ICOCR History → ICDB staged component creation."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from qt_icdb_bridge import launch_icdb


class AddBridgeTests(unittest.TestCase):
    def test_add_handoff_passes_a_single_argument_and_shared_data(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / 'icdb_qt.py').write_text("parser.add_argument('--open-part')\nparser.add_argument('--add-part')")
            (folder / 'run_qt_windows.bat').write_text('@echo off')
            data = folder / 'DATA'
            data.mkdir()
            with patch('qt_icdb_bridge.subprocess.Popen') as popen:
                launch_icdb(folder, data, 'TPS 65150', popen=popen, action='add')
            cmd = popen.call_args.args[0]
            self.assertEqual(cmd[-2:], [f'--data={Path(data).resolve()}', '--add-part=TPS 65150'])
    def test_rejects_old_icdb_for_add(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / 'icdb_qt.py').write_text("parser.add_argument('--open-part')")
            (folder / 'run_qt_windows.bat').write_text('@echo off')
            with self.assertRaisesRegex(ValueError, 'does not support Add'):
                launch_icdb(folder, folder, 'ABC', action='add')


if __name__ == '__main__':
    unittest.main()
