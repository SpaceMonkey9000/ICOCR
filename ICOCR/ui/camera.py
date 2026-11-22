"""Camera and image sources, preview frames, freeze and capture."""
import os
import sys
from pathlib import Path
import cv2
import numpy as np
from PySide6.QtWidgets import (QFileDialog, QMessageBox)
from capture import Capture
from qt_preview import PreviewWorker, render_image, PREVIEW_LIMIT


class CameraMixin:
    """Camera, opened images and the preview pipeline. Mixed into MainWindow."""

    # -- camera ----------------------------------------------------------------
    def _backend(self):
        if sys.platform == 'win32':
            return cv2.CAP_DSHOW if self.backend.currentText() == 'DirectShow' else cv2.CAP_MSMF
        return cv2.CAP_ANY

    def refresh_cameras(self):
        previous = self.devices.currentData()
        self.devices.clear()
        try:
            from cv2_enumerate_cameras import enumerate_cameras
            found = [(c.index, c.name) for c in enumerate_cameras(self._backend())]
        except Exception:
            found = []
        if not found:
            found = [(i, f'Device index {i}') for i in range(4)]
        for index, name in found:
            self.devices.addItem(f'{index}: {name}', index)
        if previous is not None and self.devices.findData(previous) >= 0:
            self.devices.setCurrentIndex(self.devices.findData(previous))

    def _peaking_options(self):
        if not self.peaking_btn.isChecked():
            return None
        return dict(colour=self.peak_colour, sensitivity=self.peak_sensitivity, opacity=self.peak_opacity)

    def start_camera(self):
        self.stop_camera()
        index = self.devices.currentData()
        if index is None:
            self.statusBar().showMessage('No device selected.')
            return
        res, fps = self.modes.currentText().split(' @')
        w, h = [int(v) for v in res.split('x')]
        self._reset_scene()
        self.frozen = None
        self.freeze_btn.setChecked(False)
        self.capture = Capture(index, self._backend(), w, h, int(fps), True)
        self.preview = PreviewWorker(self.capture, self)
        self.preview.set_peaking(self._peaking_options())
        self.preview.ready.connect(self._preview_ready)
        self.capture.start()
        self.preview.start()
        self.statusBar().showMessage('Opening camera…')

    def stop_camera(self):
        if self.preview is not None:
            worker, self.preview = self.preview, None    # late signals from it are ignored
            if worker.stop():
                worker.deleteLater()
            else:
                # Never destroy a thread that is still running: release it when it ends.
                self._retired.append(worker)
                worker.finished.connect(self._retired_finished)
        if self.capture is not None:
            self.capture.stop_event.set()
            self.capture.join(timeout=1.0)
            self.capture = None
        self._live_matrices = {}

    def _retired_finished(self):
        worker = self.sender()
        if worker in self._retired:
            self._retired.remove(worker)
            worker.deleteLater()
        self._finish_close_if_ready()

    def open_image(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Open image', '',
                                              'Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)')
        if not path:
            return
        img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            QMessageBox.warning(self, 'Image error', 'Cannot decode selected image.')
            return
        self.stop_camera()
        self._reset_scene()
        self.frozen = None
        self.freeze_btn.setChecked(False)
        self.frame = self.current_image = img
        self.refresh_preview()
        self.statusBar().showMessage(f'Opened {Path(path).name} — {img.shape[1]}×{img.shape[0]}')

    def open_image_folder(self):
        path = Path(self.documenter.capture_directory)
        if not path.is_dir():
            QMessageBox.warning(self, 'Image folder', f'Folder does not exist: {path}')
            return
        if sys.platform == 'win32':
            os.startfile(str(path))
        else:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def set_freeze(self, frozen):
        self.freeze_btn.setText('Resume' if frozen else 'Freeze')
        if frozen and self.current_image is not None:
            # Freeze exactly what is on screen, with the overlay where it is now.
            self.frozen = self.current_image
            self._frozen_matrix = (self._live_matrices.get(self._shown['epoch'])
                                   if self._shown else None)
        else:
            self.frozen = None
            self._frozen_matrix = None
        if self.preview is not None:
            self.preview.set_paused(self.frozen is not None)
        self.refresh_preview()

    def _displayed(self):
        return self.frozen if self.frozen is not None else self.current_image

    def _preview_ready(self):
        """A new camera frame is ready (already resized, peaked and tracked)."""
        worker = self.sender()
        if worker is not self.preview or worker is None:
            return
        result = worker.take()
        if result is None:
            return
        if result['frame'] is None:
            if result['status']:
                self.statusBar().showMessage(result['status'])
            return
        self.frame = result['frame']
        self._live_matrices = result['matrices']
        if self.frozen is not None:
            return
        self.current_image = self.frame
        h, w = self.frame.shape[:2]
        self.view.show_image(result['image'], (w, h))
        self._draw_overlay()

    def refresh_preview(self, *_):
        """Apply display settings. Live video picks them up on the next frame;
        a frozen frame or opened image is redrawn here."""
        if self.preview is not None:
            self.preview.set_peaking(self._peaking_options())
            if self.frozen is None:
                self._draw_overlay()
                return
        image = self._displayed()
        if image is None:
            return
        peaking = self._peaking_options()
        # Still images are shown at full resolution so zooming in stays sharp.
        # Peaking keeps the preview resolution its thresholds were tuned for.
        qimage = render_image(image, peaking, PREVIEW_LIMIT if peaking else None)
        self.view.show_image(qimage, (image.shape[1], image.shape[0]))
        self._draw_overlay()

    def take_snapshot(self):
        image = self._displayed()
        if image is None:
            self.statusBar().showMessage('No frame to capture')
        elif self.documenter.capture(image):
            self.statusBar().showMessage('Saving original full-resolution frame…')
        else:
            self.statusBar().showMessage('Capture queue full')

    def _drain_events(self):
        while True:
            try:
                kind, path, error = self.documenter.events.get_nowait()
            except Exception:
                break
            self.statusBar().showMessage(f'{kind}: {error or path}')
