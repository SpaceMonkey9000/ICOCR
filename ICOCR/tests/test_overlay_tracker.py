"""Overlay tracking accuracy on synthetic board motion (no camera, no Qt)."""
import unittest

import cv2
import numpy as np

from overlay_tracker import OverlayTracker, tracking_gray, tracking_size, move_points


def board(seed, w=1280, h=720):
    rng = np.random.default_rng(seed)
    image = np.full((h, w, 3), (40, 90, 40), np.uint8)
    for _ in range(90):
        x, y = int(rng.integers(0, w-130)), int(rng.integers(0, h-90))
        cv2.rectangle(image, (x, y), (x+int(rng.integers(30, 120)), y+int(rng.integers(20, 80))),
                      (int(rng.integers(20, 70)),)*3, -1)
        cv2.putText(image, 'IC%03d' % rng.integers(0, 999), (x+3, y+18),
                    cv2.FONT_HERSHEY_SIMPLEX, .5, (210, 210, 210), 1, cv2.LINE_AA)
    return image


def moved(image, angle, scale, tx, ty, seed=0):
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w/2, h/2), angle, scale)
    matrix[:, 2] += (tx, ty)
    frame = cv2.warpAffine(image, matrix, (w, h), borderMode=cv2.BORDER_REFLECT)
    noise = np.empty(frame.shape, np.int16)
    cv2.setRNGSeed(seed)
    cv2.randn(noise, 0, 4)
    return cv2.add(frame, noise, dtype=cv2.CV_8U), matrix


BOX = [[500, 300], [760, 300], [760, 420], [500, 420]]


class TrackerTests(unittest.TestCase):
    def setUp(self):
        self.reference = board(1)
        self.tracker = OverlayTracker(self.reference)

    def error(self, frame, truth):
        matrix = self.tracker.update(tracking_gray(frame, self.tracker.size))
        self.assertIsNotNone(matrix)
        return np.abs(np.array(move_points(BOX, matrix)) - np.array(move_points(BOX, truth))).max()

    def test_scanned_frame_is_identity(self):
        matrix = self.tracker.update(tracking_gray(self.reference, self.tracker.size))
        np.testing.assert_allclose(matrix, np.eye(2, 3), atol=.02)

    def test_follows_pan_rotation_and_zoom_without_drift(self):
        worst = 0
        for i in range(60):
            x = i/59
            frame, truth = moved(self.reference, 30*x, 1+.3*x, 200*x, -80*x, i)
            worst = max(worst, self.error(frame, truth))
        self.assertLess(worst, 2.5)
        # Returning to the start gives the start again: nothing accumulated.
        for i in range(5):
            frame, truth = moved(self.reference, 0, 1, 0, 0, 100+i)
            last = self.error(frame, truth)
        self.assertLess(last, .5)

    def test_still_board_does_not_jitter(self):
        positions = []
        for i in range(30):
            frame, _ = moved(self.reference, 0, 1, 0, 0, i)
            matrix = self.tracker.update(tracking_gray(frame, self.tracker.size))
            positions.append(move_points(BOX, matrix))
        self.assertLess(np.abs(np.diff(np.array(positions), axis=0)).max(), .15)

    def test_large_jump_between_frames_is_recovered(self):
        frame, truth = moved(self.reference, 0, 1, 260, 90)
        self.assertLess(self.error(frame, truth), 2.)

    def test_unrelated_scene_is_rejected_then_reacquired(self):
        other = tracking_gray(board(99), self.tracker.size)
        self.assertIsNone(self.tracker.update(other))
        self.assertEqual(self.tracker.lost, 1)
        self.assertIsNotNone(self.tracker.update(tracking_gray(self.reference, self.tracker.size)))

    def test_featureless_or_mismatched_frames_are_never_tracked(self):
        blank = np.full((720, 1280, 3), 128, np.uint8)
        tracker = OverlayTracker(blank)
        self.assertIsNone(tracker.update(tracking_gray(blank, tracker.size)))
        small = np.zeros((90, 160), np.uint8)
        self.assertIsNone(self.tracker.update(small))

    def test_reduced_reference_reports_full_resolution_coordinates(self):
        full = board(5, 3840, 2160)
        preview = cv2.resize(full, (1280, 720), interpolation=cv2.INTER_LINEAR)
        tracker = OverlayTracker(preview, full.shape)
        self.assertEqual(tracker.size, tracking_size(full.shape))
        shifted, _ = moved(preview, 0, 1, 40, -20)       # 40 preview px = 120 full px
        matrix = tracker.update(tracking_gray(shifted, tracker.size))
        np.testing.assert_allclose(matrix[:, 2], (120, -60), atol=1.5)


if __name__ == '__main__':
    unittest.main()
