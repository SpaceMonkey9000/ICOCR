"""Headless end-to-end check of the Qt window: preview, scan, overlay tracking.

Uses a synthetic camera and a stub OCR reader, so it needs no device, models or
database. Run with:  python -m unittest tests.test_qt_window
"""
import os
import tempfile
import time
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
_HOME = tempfile.mkdtemp(prefix='icocr-test-')
os.environ.setdefault('ICLENS_DATA', os.path.join(_HOME, 'DATA'))
os.environ.setdefault('ICOCR_CONFIG_DIR', os.path.join(_HOME, 'config'))

import cv2
import numpy as np

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                   # pragma: no cover
    QApplication = None

W, H, STEP = 1920, 1080, 3.0      # the synthetic board moves 3 px right per frame


def board():
    rng = np.random.default_rng(7)
    image = np.full((H, W, 3), (40, 90, 40), np.uint8)
    for _ in range(120):
        x, y = int(rng.integers(0, W-160)), int(rng.integers(0, H-110))
        cv2.rectangle(image, (x, y), (x+int(rng.integers(40, 150)), y+int(rng.integers(30, 100))),
                      (int(rng.integers(20, 70)),)*3, -1)
        cv2.putText(image, 'IC%03d' % rng.integers(0, 999), (x+4, y+22),
                    cv2.FONT_HERSHEY_SIMPLEX, .6, (210, 210, 210), 1, cv2.LINE_AA)
    return image


@unittest.skipIf(QApplication is None, 'PySide6 is not installed')
class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from user_paths import prepare_config
        from project_paths import DATA
        prepare_config(DATA)
        import capture
        import qt_window
        cls.qt_window = qt_window
        base = board()

        class FakeCapture(capture.Capture):
            """Publishes a board sliding right; frame n is shifted by n*STEP px."""
            def run(self):
                n = 0
                while not self.stop_event.is_set():
                    shift = np.float64([[1, 0, n*STEP], [0, 1, 0]])
                    frame = cv2.warpAffine(base, shift, (W, H), borderMode=cv2.BORDER_REFLECT)
                    frame.flags.writeable = False     # consumers must never modify frames
                    with self.lock:
                        self.latest, self.status = frame, f'{W} × {H} received'
                        self.seq = n = n + 1
                        self.offsets = getattr(self, 'offsets', {})
                        self.offsets[id(frame)] = (n-1)*STEP
                        self.lock.notify_all()
                    time.sleep(1/30)
                with self.lock:
                    self.finished = True
                    self.lock.notify_all()

        class StubOCR:
            last_diagnostics = {}

            def warm_up(self):
                pass

        def read_with_body(ocr, crop, **options):
            time.sleep(.3)                            # a scan takes a while; video must not stall
            row = dict(key='SN74HC00', text='SN74HC00', score=.97, kind='candidate',
                       box=[[20, 30], [220, 30], [220, 80], [20, 80]])
            ocr.last_diagnostics = dict(
                body_detection=dict(box=[[5, 5], [300, 5], [300, 200], [5, 200]]),
                scan_result=dict(selected=row, provisional=None, candidates=[row], all_candidates=[row]))
            return [row], .3

        import ui.workers
        import ui.camera
        ui.camera.Capture = FakeCapture
        ui.workers.shared_ocr = lambda: StubOCR()
        ui.workers.read_with_body = read_with_body
        cls.app = QApplication.instance() or QApplication([])
        cls.window = qt_window.MainWindow()
        cls.window.live_recognition.setChecked(False)
        cls.window.devices.clear()
        cls.window.devices.addItem('0: synthetic', 0)
        cls.window.show()

    @classmethod
    def tearDownClass(cls):
        cls.window.close()
        deadline = time.monotonic() + 5
        while not cls.window._close_finalized and time.monotonic() < deadline:
            cls.app.processEvents()
            time.sleep(.01)
        assert cls.window._close_finalized

    def pump(self, seconds=None, until=None, limit=6.):
        deadline = time.monotonic() + (seconds if seconds is not None else limit)
        while time.monotonic() < deadline:
            self.app.processEvents()
            if until is not None and until():
                return True
            time.sleep(.002)
        return until is None

    def overlay_offset(self):
        """Horizontal overlay translation minus the true board motion (px)."""
        window = self.window
        truth = window.capture.offsets
        return (window.recognition_overlay.root.transform().dx()
                - (truth[id(window.current_image)] - truth[id(window._shown['frame'])]))

    def test_diagnostics_zip_matches_the_scanned_frame(self):
        from pathlib import Path
        from zipfile import ZipFile

        window = self.window
        original_directory = window.diagnostics_directory
        original_tab = window.tabs.currentIndex()
        window.start_camera()
        try:
            with tempfile.TemporaryDirectory() as directory:
                window.diagnostics_directory = Path(directory)
                window._set_diagnostics_enabled(True)
                window.tabs.setCurrentIndex(window.diagnostic_tab_index)
                self.assertTrue(self.pump(until=lambda: window.current_image is not None))
                window.scan()
                self.assertTrue(self.pump(until=window.diagnostic_export_btn.isEnabled))
                frame = window._shown['frame']
                report = window.diagnostic_text.toPlainText()
                window.diagnostic_export_btn.click()
                window.diagnostic_export_btn.click()
                path = Path(directory) / 'SN74HC00.zip'
                collision = Path(directory) / 'SN74HC00_2.zip'
                self.assertTrue(self.pump(until=lambda: collision.is_file()
                                          and window.statusBar().currentMessage().endswith(collision.name)))
                for saved in (path, collision):
                    with ZipFile(saved) as archive:
                        self.assertEqual(set(archive.namelist()), {'camera.png', 'camera_overlay.png', 'diagnostics.txt'})
                        self.assertEqual(archive.read('diagnostics.txt').decode(), report)
                        images = [cv2.imdecode(np.frombuffer(archive.read(name), np.uint8), cv2.IMREAD_COLOR)
                                  for name in ('camera.png', 'camera_overlay.png')]
                        np.testing.assert_array_equal(images[0], frame)
                        self.assertEqual(images[1].shape, frame.shape)
                        np.testing.assert_array_equal(images[1][0, 0], frame[0, 0])
                        self.assertGreater(np.count_nonzero(images[0] != images[1]), 100)
        finally:
            window._set_diagnostics_enabled(False)
            window.diagnostics_directory = original_directory
            window.tabs.setCurrentIndex(original_tab)
            window.stop_camera()

    def test_preview_scan_overlay_freeze_and_live(self):
        window, overlay = self.window, self.window.recognition_overlay
        window.start_camera()
        self.assertTrue(self.pump(until=lambda: window.current_image is not None))
        # The status bar no longer shows a preview rate, so count displayed frames.
        shown, show_image = [], window.view.show_image
        window.view.show_image = lambda *a, **k: (shown.append(1), show_image(*a, **k))
        started = time.perf_counter()
        self.pump(1.2)
        window.view.show_image = show_image
        self.assertEqual(window.view.source_size, (W, H))
        fps = len(shown) / (time.perf_counter() - started)
        self.assertGreater(fps, 20, f'{fps:.1f} frames/s displayed')

        # Manual scan: the preview keeps running while OCR works.
        window.view.set_roi((.3, .3, .7, .7))
        before = window.capture.seq
        window.scan()
        # A pending manual scan must not discard previously detected bodies.
        self.assertTrue(self.pump(until=lambda: window._shown is not None))
        self.assertGreater(window.capture.seq - before, 5)
        self.assertEqual(overlay.count, 2)                 # body outline + marking
        self.assertEqual(len(overlay.labels), 1)
        self.assertEqual(window.results.count(), 1)

        # The overlay follows the moving board, in step with the displayed frame.
        errors = []
        for _ in range(25):
            self.pump(.04)
            self.assertTrue(overlay.root.isVisible())
            errors.append(abs(self.overlay_offset()))
        self.assertLess(max(errors), 1.5, errors)
        # Polygon is stored in scan-frame pixels: ROI origin + OCR box.
        polygon = overlay.root.childItems()[1].polygon()
        self.assertEqual((polygon[0].x(), polygon[0].y()), (int(.3*W)+20, int(.3*H)+30))

        # Freeze keeps the overlay where it was on the frozen frame.
        window.freeze_btn.setChecked(True)
        frozen_offset = self.overlay_offset()
        self.pump(.3)
        self.assertTrue(overlay.root.isVisible())
        self.assertAlmostEqual(self.overlay_offset(), frozen_offset, places=6)
        self.assertLess(abs(frozen_offset), 1.5)
        self.assertEqual(window.view.pix_item.pixmap().width(), W)   # frozen frame is full resolution
        window.freeze_btn.setChecked(False)
        self.pump(.3)
        self.assertLess(abs(self.overlay_offset()), 1.5)

        # Live recognition: outlines stay visible while the next scan runs.
        shown = window._shown['epoch']
        window.scan(live=True)
        hidden = []
        self.assertTrue(self.pump(until=lambda: hidden.append(not overlay.root.isVisible())
                                  or window._shown['epoch'] != shown))
        self.assertGreater(len(hidden), 20)
        self.assertFalse(any(hidden))
        self.pump(.2)
        self.assertTrue(overlay.root.isVisible())
        self.assertLess(abs(self.overlay_offset()), 1.5)

        # Switching the overlay off hides it; focus peaking does not disturb tracking.
        window.overlay_enabled = False
        window.refresh_preview()
        self.pump(.1)
        self.assertFalse(overlay.root.isVisible())
        window.overlay_enabled = True
        window.peaking_btn.setChecked(True)
        self.pump(.3)
        self.assertTrue(overlay.root.isVisible())
        self.assertLess(abs(self.overlay_offset()), 1.5)
        window.peaking_btn.setChecked(False)

        # Restarting the camera discards old results.
        window.start_camera()
        self.assertEqual(overlay.count, 0)
        window.stop_camera()


if __name__ == '__main__':
    unittest.main()
