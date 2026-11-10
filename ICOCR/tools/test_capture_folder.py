"""Capture destination checks, independent of camera and OCR models."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from documentation import Documentation
from user_paths import capture_directory, default_capture_directory


class CaptureFolderTests(unittest.TestCase):
    def test_default_and_saved_preference(self):
        self.assertEqual(capture_directory({}), default_capture_directory())
        self.assertEqual(capture_directory({'capture_folder': ''}), default_capture_directory())
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(capture_directory({'capture_folder': td}), Path(td).resolve())

    def test_capture_destination_numbering_and_confirmed_log(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            captures = base/'Pictures'/'ICOCR'
            writer = Documentation(base/'DATA', captures)
            frame = np.zeros((16, 24, 3), dtype=np.uint8)
            self.assertTrue(writer.capture(frame))
            kind, path, error = writer.events.get(timeout=5)
            self.assertEqual((kind, error), ('capture', None))
            self.assertEqual(path, captures/'IC_000001.jpg')
            self.assertEqual(cv2.imread(str(path)).shape, frame.shape)
            writer.close(5)
            # Restart resumes numbering, including older PNG files.
            (captures/'IC_000009.png').write_bytes(b'older capture')
            writer = Documentation(base/'DATA', captures)
            self.assertTrue(writer.capture(frame))
            self.assertEqual(writer.events.get(timeout=5)[1], captures/'IC_000010.jpg')
            self.assertTrue(writer.confirm(frame, {'part_number': 'TEST'}))
            kind, path, error = writer.events.get(timeout=5)
            self.assertEqual((kind, error), ('confirm', None))
            self.assertEqual(path.parent, base/'DATA'/'confirmed')
            self.assertTrue((path.parent/'confirmed.csv').exists())
            self.assertFalse((base/'DATA'/'captures').exists())
            writer.close(5)

    def test_queued_capture_keeps_destination_when_setting_changes(self):
        with tempfile.TemporaryDirectory() as td:
            old, new = Path(td)/'old', Path(td)/'new'
            writer = Documentation(Path(td)/'DATA', old)
            frame = np.zeros((8, 8, 3), dtype=np.uint8)
            with patch.object(writer, '_submit', return_value=True) as submit:
                writer.capture(frame)
                job = submit.call_args.args
            writer.capture_directory = new
            path = job[1](*job[2:])
            self.assertEqual(path.parent, old)
            self.assertTrue(writer.capture(frame))
            self.assertEqual(writer.events.get(timeout=5)[1].parent, new)
            writer.close(5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
