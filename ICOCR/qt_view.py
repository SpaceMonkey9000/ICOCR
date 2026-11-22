"""Zoomable image view with the scan-region rectangle.

Scene coordinates are always full-resolution source pixels, whatever size the
displayed preview pixmap has. Zoom, scroll position, the scan region and the
recognition overlay therefore stay put when the preview resolution changes
(live preview <-> frozen full-resolution frame).
"""
from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QPixmap, QPen, QColor, QPainter, QTransform
from PySide6.QtWidgets import (QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
                               QGraphicsRectItem)

DEFAULT_ROI = (.3, .2, .7, .8)


class ImageView(QGraphicsView):
    region_changed = Signal(tuple)
    view_changed = Signal()      # zoom or scroll position changed
    body_clicked = Signal(tuple)  # normalized source ROI for clicked body

    def __init__(self):
        super().__init__()
        self.canvas = QGraphicsScene(self)
        # Items move every frame; a BSP index would be rebuilt constantly.
        self.canvas.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)
        self.setScene(self.canvas)
        self.pix_item = QGraphicsPixmapItem()
        self.pix_item.setTransformationMode(Qt.TransformationMode.FastTransformation)
        self.canvas.addItem(self.pix_item)
        self.rect_item = QGraphicsRectItem()
        pen = QPen(QColor('#57db9d'), 2)
        pen.setCosmetic(True)           # constant on-screen width at any zoom
        self.rect_item.setPen(pen)
        self.rect_item.setBrush(QColor(60, 200, 150, 22))
        self.rect_item.setZValue(10)
        self.canvas.addItem(self.rect_item)
        self.roi = DEFAULT_ROI
        self.body_hit_tester = None
        self.drag_start = None
        self._pan_from = None
        self._auto_fit = True
        self._source_size = (0, 0)
        self._pixmap_size = (0, 0)
        self.setBackgroundBrush(QColor('#141a20'))
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # The whole picture changes every frame: skip dirty-region bookkeeping.
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontSavePainterState, True)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setMinimumSize(360, 250)
        self.setStyleSheet('border:0;')

    @property
    def source_size(self):
        return self._source_size

    def show_image(self, image, source_size):
        """Display ``image`` (QImage) standing for a ``source_size`` (w, h) frame."""
        self.pix_item.setPixmap(QPixmap.fromImage(image))
        size = (image.width(), image.height())
        source_size = tuple(source_size)
        if size != self._pixmap_size or source_size != self._source_size:
            self._pixmap_size = size
            self.pix_item.setTransform(QTransform.fromScale(
                source_size[0]/max(1, size[0]), source_size[1]/max(1, size[1])))
        if source_size != self._source_size:
            self._source_size = source_size
            self.canvas.setSceneRect(QRectF(0, 0, *source_size))
            self.fit_image()
            self.draw_roi()

    def draw_roi(self):
        w, h = self._source_size
        if w and h:
            x1, y1, x2, y2 = self.roi
            self.rect_item.setRect(QRectF(x1*w, y1*h, (x2-x1)*w, (y2-y1)*h))

    def set_roi(self, roi):
        self.roi = tuple(roi)
        self.draw_roi()

    def fit_image(self):
        self._auto_fit = True
        if self._source_size != (0, 0):
            self.fitInView(self.canvas.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            self.view_changed.emit()

    # -- mouse -----------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._source_size != (0, 0):
            scene_point = self.mapToScene(event.position().toPoint())
            if self.body_hit_tester is not None:
                body_roi = self.body_hit_tester(scene_point, self._source_size)
                if body_roi is not None:
                    self.body_clicked.emit(body_roi)
                    event.accept()
                    return
            self.drag_start = scene_point
            event.accept()
        elif event.button() == Qt.MouseButton.MiddleButton:
            self._auto_fit = False
            self._pan_from = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.set_roi(DEFAULT_ROI)
            self.region_changed.emit(self.roi)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drag_start is not None:
            self._update_region(self.drag_start, self.mapToScene(event.position().toPoint()))
        elif self._pan_from is not None:
            point = event.position().toPoint()
            delta = point - self._pan_from
            self._pan_from = point
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.drag_start is not None and event.button() == Qt.MouseButton.LeftButton:
            self._update_region(self.drag_start, self.mapToScene(event.position().toPoint()))
            self.drag_start = None
            self.region_changed.emit(self.roi)
        elif self._pan_from is not None and event.button() == Qt.MouseButton.MiddleButton:
            self._pan_from = None
            self.unsetCursor()
        else:
            super().mouseReleaseEvent(event)

    def _update_region(self, a, b):
        w, h = self._source_size
        if not w or not h:
            return
        x1, x2 = sorted((max(0, min(1, a.x()/w)), max(0, min(1, b.x()/w))))
        y1, y2 = sorted((max(0, min(1, a.y()/h)), max(0, min(1, b.y()/h))))
        if (x2-x1)*w >= 12 and (y2-y1)*h >= 12:
            self.set_roi((x1, y1, x2, y2))

    def wheelEvent(self, event):
        if self._source_size == (0, 0) or not event.angleDelta().y():
            return
        factor = 1.2 if event.angleDelta().y() > 0 else 1/1.2
        if 0.02 < self.transform().m11()*factor < 40:
            self._auto_fit = False
            self.scale(factor, factor)
            self.view_changed.emit()

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        self.view_changed.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._auto_fit and self._source_size != (0, 0):
            self.fit_image()
        self.view_changed.emit()
