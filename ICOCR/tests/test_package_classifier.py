"""Classifier boundary, fail-open behavior, and scan integration regressions."""
import json
import os
import sys
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('ICOCR_RULES_DIR', str(ROOT/'factory'/'rules'))
sys.path.insert(0, str(ROOT))
import package_classifier as package
from body_scan import read_with_body


class PackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        fixture = Path(cls.directory.name)/'DATA'/'models'
        fixture.mkdir(parents=True)
        for name in ('package_classifier.onnx', 'package_classifier.json'):
            shutil.copy2(ROOT/'models'/name, fixture/name)
        cls.model = fixture/'package_classifier.onnx'
        cls.classifier = package.PackageClassifier(cls.model)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_bundled_contract(self):
        self.assertEqual(self.classifier.classes, ['QF', 'SOP', 'TO'])

    def test_runtime_path_has_no_application_folder_fallback(self):
        with patch.object(package, 'DATA', Path('/shared/ICSuite/DATA')):
            self.assertEqual(package.default_model(), Path('/shared/ICSuite/DATA/models/package_classifier.onnx'))

    def test_bgr_rgb_margin_and_normalization(self):
        image = np.zeros((80, 160, 3), np.uint8)
        image[:, :, 2] = 255
        sample = package.input_array(image)
        self.assertEqual(sample.shape, (1, 3, 224, 224))
        np.testing.assert_array_equal(sample[0, :, 112, 112], [1., 0., 0.])
        np.testing.assert_allclose(sample[0, :, 0, 0], np.repeat(114/255, 3))

    def test_advisory_probability_result(self):
        result = self.classifier.predict(np.zeros((80, 160, 3), np.uint8))
        self.assertEqual(len(result['candidates']), 3)
        self.assertTrue(result['advisory'])
        self.assertAlmostEqual(sum(c['confidence'] for c in result['candidates']), 1., places=5)
        json.dumps(result)

    def test_low_confidence_preserves_best_class(self):
        with patch.object(self.classifier.session, 'run', return_value=[np.array([[.4, .35, .25]])]):
            result = self.classifier.predict(np.zeros((20, 20, 3), np.uint8), .5)
        self.assertEqual(result['package'], 'unknown')
        self.assertEqual(result['best_class'], 'QF')

    def test_invalid_output_rejected(self):
        for values in ([np.nan, .5, .5], [.5, .5, .5], [-.1, .5, .6]):
            with self.subTest(values=values), patch.object(self.classifier.session, 'run', return_value=[np.array([values])]):
                with self.assertRaises(ValueError):
                    self.classifier.predict(np.zeros((20, 20, 3), np.uint8))

    def test_missing_model_does_not_abort(self):
        result = package.classify_region(np.zeros((30, 30, 3), np.uint8),
            options=dict(enabled=True, model='/missing/package.onnx'))
        self.assertEqual(result['status'], 'unavailable')

    def test_disabled_does_not_load(self):
        with patch.object(package, 'shared_classifier', side_effect=AssertionError('must not load')):
            self.assertEqual(package.classify_region(None)['status'], 'disabled')

    def test_padded_region_keeps_original_pixels(self):
        image = np.zeros((100, 200, 3), np.uint8)
        image[20:80, 40:160] = 255
        seen = []
        fake = SimpleNamespace(predict=lambda im, threshold: seen.append(im.copy()) or dict(status='classified', package='SOP'))
        detection = dict(status='detected', box=[[60, 30], [140, 30], [140, 70], [60, 70]])
        with patch.object(package, 'shared_classifier', return_value=(fake, None)):
            result = package.classify_region(image, detection, dict(enabled=True))
        self.assertEqual(result['crop_bounds'], [40, 20, 160, 80])
        np.testing.assert_array_equal(seen[0], image[20:80, 40:160])

    def test_metadata_and_hash_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory)/'package.onnx'
            model.write_bytes(self.model.read_bytes())
            meta = json.loads(self.model.with_suffix('.json').read_text())
            sidecar = model.with_suffix('.json')
            meta['kind'] = 'logo_classification'
            sidecar.write_text(json.dumps(meta))
            with self.assertRaises(ValueError):package.contract(model)
            meta['kind'] = 'package_classification'
            sidecar.write_text(json.dumps(meta))
            model.write_bytes(b'corrupt')
            with self.assertRaises(ValueError):package.contract(model)

    def test_permuted_sidecar_class_order_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory)/'package.onnx'
            model.write_bytes(self.model.read_bytes())
            meta = json.loads(self.model.with_suffix('.json').read_text())
            meta['classes'] = ['SOP', 'QF', 'TO']
            model.with_suffix('.json').write_text(json.dumps(meta))
            with self.assertRaisesRegex(ValueError, 'class order'):
                package.PackageClassifier(model)

    def test_scan_keeps_ocr_result_when_package_unavailable(self):
        class Engine:
            def read(self, image, **options):
                self.last_diagnostics = dict(scan_result=dict(selected=None, selected_marking=''), timings={})
                return [], 0.
        engine = Engine()
        rows, elapsed = read_with_body(engine, np.zeros((40, 60, 3), np.uint8),
            package_options=dict(enabled=True, model='/missing/package.onnx'))
        self.assertEqual(rows, [])
        self.assertEqual(engine.last_diagnostics['scan_result']['selected_marking'], '')
        self.assertEqual(engine.last_diagnostics['package_classification']['status'], 'unavailable')
        self.assertGreaterEqual(elapsed, 0.)

    def test_scan_uses_unmasked_package_image(self):
        class Engine:
            def read(self, image, **options):
                self.last_diagnostics = dict(timings={})
                return [], 0.
        original = np.full((40, 60, 3), 255, np.uint8)
        with patch.object(package, 'classify_region', return_value=dict(status='classified', package='TO', milliseconds=1)) as classify:
            read_with_body(Engine(), np.zeros_like(original), package_image=original, package_options=dict(enabled=True))
        self.assertIs(classify.call_args.args[0], original)


    def test_full_frame_context_preserves_leads_outside_ocr_selection(self):
        frame = np.zeros((200, 320, 3), np.uint8)
        frame[30:150, 100:220] = 255
        # A body at frame [120,50]..[200,130], selected tightly for OCR.
        detection = dict(status='detected', box=[[0, 0], [80, 0], [80, 80], [0, 80]])
        fake = SimpleNamespace(predict=lambda im, threshold: dict(status='classified', package='SOP'))
        with patch.object(package, 'shared_classifier', return_value=(fake, None)):
            result = package.classify_scan(frame[50:130, 120:200], detection,
                dict(enabled=True), frame, (.375, .25, .625, .65))
        self.assertEqual(result['crop_bounds'], [100, 30, 220, 150])
        self.assertEqual(result['crop_space'], 'frame')



if __name__ == '__main__':
    unittest.main()
