"""Render the overlay on the exact source frame used by recognition."""
import numpy as np
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter

from qt_preview import render_image
from qt_recognition_overlay import RecognitionOverlay
from qt_view import ImageView


def annotated_frame(scan, database_loaded):
    frame = scan['frame']
    height, width = frame.shape[:2]
    view = ImageView()
    try:
        view.set_roi(scan['roi'])
        view.show_image(render_image(frame, None, None), (width, height))
        overlay = RecognitionOverlay(view)
        overlay.set_results(scan['rows'], scan['bodies'], scan['roi'], (width, height), database_loaded)
        overlay.draw()
        for item, anchor in overlay.labels:
            item.set_below(anchor.y() < item.height)

        result = QImage(width, height, QImage.Format.Format_BGR888)
        if result.isNull():
            raise OSError('Could not allocate the annotated image')
        painter = QPainter(result)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            view.canvas.render(painter, QRectF(0, 0, width, height))
        finally:
            painter.end()
        pixels = np.frombuffer(result.constBits(), dtype=np.uint8)
        return pixels.reshape(height, result.bytesPerLine())[:, :width * 3].reshape(frame.shape).copy()
    finally:
        view.deleteLater()
