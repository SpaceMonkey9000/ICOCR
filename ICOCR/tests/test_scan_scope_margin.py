"""Regression tests for scan mode independence and selected-body movement tolerance."""
import ast
from pathlib import Path
import unittest
from qt_scan_region import expand_body_roi


class CropMarginTests(unittest.TestCase):
    def test_margin_normalized_and_clamped(self):
        x0, y0, x1, y1 = expand_body_roi((.4, .3, .6, .5), (1000, 500))
        self.assertAlmostEqual(x0, .37)
        self.assertAlmostEqual(x1, .63)
        self.assertAlmostEqual(y0, .268)
        self.assertAlmostEqual(y1, .532)

    def test_edge_clamping(self):
        self.assertEqual(expand_body_roi((0, 0, .1, .1), (1000, 1000))[:2], (0., 0.))
        self.assertEqual(expand_body_roi((.9, .9, 1, 1), (1000, 1000))[2:], (1., 1.))

    def test_small_chip_minimum_margin(self):
        roi = expand_body_roi((.5, .5, .51, .51), (1000, 1000))
        self.assertAlmostEqual((.5 - roi[0]) * 1000, 16.)
        self.assertAlmostEqual((roi[3] - .51) * 1000, 16.)

    def test_invalid_roi(self):
        with self.assertRaises(ValueError):
            expand_body_roi((.5, .3, .5, .7), (1000, 1000))


class ScanModeSourceTests(unittest.TestCase):
    def test_body_only_does_not_force_multi(self):
        # The main window's code is in qt_window.py and the ui/ package.
        root = Path(__file__).resolve().parents[1]
        src = '\n'.join(path.read_text(encoding='utf-8') for path in
                        [root / 'qt_window.py', *sorted((root / 'ui').rglob('*.py'))])
        self.assertIn("if self.options.get('multi'):", src)
        self.assertNotIn("if self.options.get('multi') or self.options.get('body_only'):", src)
        self.assertIn("body_only=bool(self.options.get('body_only'))", src)
        self.assertIn('multi=self.multi_enabled,', src)
        self.assertIn('self.scan_mode.addItem(\'Single chip\', False)', src)
        self.assertIn('self.scan_mode.addItem(\'Multiple chips\', True)', src)

if __name__ == '__main__':
    unittest.main()
