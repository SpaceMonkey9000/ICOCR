"""Regression coverage for Qt2 interaction/theme changes and detector-only OCR planning."""
import unittest
from unittest.mock import patch
import numpy as np
import multi_chip
from pathlib import Path
import ast


class ThemeTests(unittest.TestCase):
    def test_icdb_native_theme_structure(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / 'qt_theme.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        theme_assign = next(node for node in tree.body if isinstance(node, ast.Assign)
                            and any(isinstance(target, ast.Name) and target.id == 'THEMES' for target in node.targets))
        self.assertEqual(set(ast.literal_eval(theme_assign.value)), {'light', 'dark'})
        self.assertIn("'#30343B'", source)
        self.assertIn("'#F0F0F0'", source)
        self.assertIn('apply_palette', source)
        self.assertNotIn('application_stylesheet', source)
        self.assertNotIn('border-radius:0px', source)
        # The main window's code is in qt_window.py and the ui/ package.
        window = '\n'.join(path.read_text(encoding='utf-8') for path in
                           [root / 'qt_window.py', *sorted((root / 'ui').rglob('*.py'))])
        self.assertIn('apply_palette(app, is_dark(self.theme))', window)
        self.assertIn('normalized_theme(', window)


class BodyOnlyTests(unittest.TestCase):
    def setUp(self):
        self.image = np.zeros((300, 400, 3), dtype=np.uint8)
        self.detections = [dict(
            box=[60, 50, 180, 140],
            polygon=[[60, 50], [180, 50], [180, 140], [60, 140]],
            mask_polygon=[[60, 50], [180, 50], [180, 140], [60, 140]],
            score=.94,
        )]

    def test_no_ocr_discovery_or_chip_when_no_detections(self):
        with patch.object(multi_chip, 'discover_lines', side_effect=AssertionError('OCR discovery called')):
            plan = multi_chip.plan(None, self.image, detections=[], detector_only=True)
        self.assertEqual(plan['chips'], [])
        self.assertEqual(plan['discovery_passes'], 0)

    def test_detector_only_plan_uses_body_without_ocr_discovery(self):
        with patch.object(multi_chip, 'discover_lines', side_effect=AssertionError('OCR discovery called')):
            plan = multi_chip.plan(None, self.image, detections=self.detections, detector_only=True)
        self.assertEqual(len(plan['chips']), 1)
        self.assertEqual(plan['chips'][0]['source'], 'detector')
        self.assertEqual(plan['discovery_passes'], 0)

    def test_read_chips_disables_full_image_recovery(self):
        class Stub:
            last_diagnostics = {}
        engine = Stub()
        calls = []
        def fake_read(ocr, crop, **options):
            calls.append(options)
            ocr.last_diagnostics = {'body_detection': {'status': 'applied', 'box': [[0,0],[10,0],[10,10],[0,10]]}, 'scan_result': {'selected': None, 'provisional': None, 'all_candidates': []}}
            return [], 0.01
        with patch.object(multi_chip, 'discover_lines', side_effect=AssertionError('OCR discovery called')):
            chips, summary = multi_chip.read_chips(engine, self.image, read=fake_read, detections=self.detections, detector_only=True)
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0]['allow_recovery'], False)
        self.assertEqual(summary['discovery_passes'], 0)

if __name__ == '__main__':
    unittest.main()
