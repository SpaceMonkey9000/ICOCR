"""Focus aid and clean-frame isolation regression checks (no camera)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from documentation import Documentation
from focus_peaking import DEFAULTS, COLOURS, overlay, options


def sample():
    image = np.full((240, 480, 3), 90, np.uint8)
    cv2.putText(image, 'IC OCR 123', (15, 120), cv2.FONT_HERSHEY_SIMPLEX,
                1.6, (230, 230, 230), 2, cv2.LINE_AA)
    return image


def highlighted(image, **kwargs):
    return np.any(overlay(image, **kwargs) != image, axis=2)


class FocusPeakingTests(unittest.TestCase):
    def test_defocus_reduces_highlights_without_frame_normalization(self):
        sharp = sample()
        soft = cv2.GaussianBlur(sharp, (0, 0), 4)
        self.assertGreater(highlighted(sharp).sum(), 1000)
        self.assertLess(highlighted(soft).sum(), highlighted(sharp).sum() // 10)

    def test_flat_image_has_no_peaking(self):
        for level in (0, 90, 255):
            flat = np.full((32, 32, 3), level, np.uint8)
            np.testing.assert_array_equal(overlay(flat, sensitivity='High'), flat)

    def test_sensitivity_adds_weaker_edges(self):
        image = sample()
        low, medium, high = [highlighted(image, sensitivity=v) for v in ('Low', 'Medium', 'High')]
        self.assertTrue(np.all(~low | medium))
        self.assertTrue(np.all(~medium | high))
        self.assertGreater(high.sum(), low.sum())

    def test_colours_opacity_and_original_frame_unchanged(self):
        image = sample()
        original = image.copy()
        for name, bgr in COLOURS.items():
            full = overlay(image, colour=name, opacity='100%')
            mask = np.any(full != image, axis=2)
            self.assertTrue(mask.any())
            np.testing.assert_array_equal(full[mask], np.tile(bgr, (mask.sum(), 1)))
            half = overlay(image, colour=name, opacity='50%')
            np.testing.assert_array_equal(half[mask], np.rint(image[mask] * .5 + np.array(bgr) * .5))
        np.testing.assert_array_equal(image, original)

    def test_missing_invalid_settings_fall_back(self):
        self.assertEqual(options({}), DEFAULTS)
        self.assertEqual(options(dict(peaking_colour=[], peaking_sensitivity=99, peaking_opacity=None)), DEFAULTS)



    def test_saved_photo_uses_clean_frame_while_overlay_is_visible(self):
        frame = sample()
        preview = overlay(frame)
        self.assertTrue(np.any(preview != frame))
        with tempfile.TemporaryDirectory() as td:
            writer = Documentation(Path(td)/'DATA', Path(td)/'photos')
            try:
                self.assertTrue(writer.capture(frame))
                kind, path, error = writer.events.get(timeout=5)
                self.assertEqual((kind, error), ('capture', None))
                # Compare identical JPEG encoding, avoiding lossy pixel-equality assumptions.
                self.assertEqual(path.read_bytes(), writer._jpeg(frame, writer.CAPTURE_JPEG_QUALITY))
            finally:
                writer.close(5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
