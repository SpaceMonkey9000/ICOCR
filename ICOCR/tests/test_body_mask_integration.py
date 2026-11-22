"""Model crop mask and full-frame outline regression tests (no Qt dependency)."""
import unittest
import numpy as np
import cv2
from body_locator import body_crop
from ic_body_detector import for_roi

class BodyMaskTests(unittest.TestCase):
    def test_polygon_crop_neutralizes_background(self):
        image = np.full((100, 140, 3), 70, dtype=np.uint8)
        polygon = [[30,30],[95,32],[83,80],[42,85]]
        cv2.fillPoly(image, [np.array(polygon, np.int32)], (10,50,170))
        body = dict(status='detected', source='model',
                    box=[[30,30],[95,30],[95,85],[30,85]],
                    mask_polygon=polygon)
        work, offset = body_crop(image, body)
        self.assertLess(work.shape[0], image.shape[0])
        self.assertLess(work.shape[1], image.shape[1])
        # Outside the polygon, background is neutralised to an on-body colour.
        self.assertGreater(int(work[0,0,2]), 100)
        self.assertEqual(len(offset), 2)

    def test_roi_conversion_preserves_mask(self):
        polygon = [[30,30],[95,32],[83,80],[42,85]]
        detections = [dict(box=[30,30,95,85], polygon=[[30,30],[95,30],[95,85],[30,85]],
                           mask_polygon=polygon, score=.92)]
        d = for_roi(detections, (.1,.1,.8,.9), (100,140,3))
        self.assertEqual(d['source'], 'model')
        self.assertEqual(len(d['mask_polygon']), 4)
        self.assertAlmostEqual(d['mask_polygon'][0][0], 16.)

if __name__ == '__main__': unittest.main()
