"""Regression: segmentation contours resolve to straight package edges and crop."""
import unittest
import numpy as np
import cv2
from ic_body_detector import _straight_body_polygon, for_roi
from body_locator import body_crop


class StraightPackageGeometryTests(unittest.TestCase):
    def test_rotated_contour_produces_four_straight_edges(self):
        raw = cv2.boxPoints(((100, 90), (110, 55), 28)).astype(np.float32)
        mask = raw.tolist() + [((raw[0]+raw[1])/2 + [3,3]).tolist()]
        box = _straight_body_polygon(mask, [[0,0],[200,0],[200,200],[0,200]])
        self.assertEqual(len(box), 4)
        sides = [np.asarray(box[(i+1)%4])-np.asarray(box[i]) for i in range(4)]
        self.assertAlmostEqual(float(sides[0][0]*sides[2][1]-sides[0][1]*sides[2][0]), 0., delta=1e-2)
        self.assertAlmostEqual(float(sides[1][0]*sides[3][1]-sides[1][1]*sides[3][0]), 0., delta=1e-2)
        self.assertGreater(abs(box[0][1]-box[1][1]), 1)

    def test_crop_follows_straight_polygon_not_mask(self):
        image = np.full((160,180,3), 160, np.uint8)
        straight = cv2.boxPoints(((85,80),(100,55),30)).tolist()
        # A deliberately smaller, irregular silhouette must not shrink crop.
        small = [[65,65],[103,70],[97,92],[68,89],[62,78]]
        d = dict(box=straight,mask_polygon=small,status='detected')
        crop, offset = body_crop(image,d)
        bounds = np.asarray(straight)
        self.assertLessEqual(offset[0], bounds[:,0].min())
        self.assertLessEqual(offset[1], bounds[:,1].min())
        self.assertGreaterEqual(crop.shape[1]+offset[0], bounds[:,0].max())
        self.assertGreaterEqual(crop.shape[0]+offset[1], bounds[:,1].max())

    def test_roi_preserves_straight_corners(self):
        straight=[[40,30],[110,45],[101,90],[31,75]]
        result=for_roi([dict(box=[31,30,110,90],polygon=straight,
                             mask_polygon=[[50,40],[90,50],[77,75]],score=.95)],
                       (0,0,1,1),(140,180,3))
        self.assertEqual(result['box'], straight)

if __name__ == '__main__': unittest.main()
