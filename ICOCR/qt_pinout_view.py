"""Interactive, read-only pinout viewport for Identify and History.

Wheel zooms about cursor; left/middle drag pans; double click fits. The source
pixmap and ICDB reference are never modified.
"""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QPixmap, QColor
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QFrame


class PinoutView(QGraphicsView):
    def __init__(self, placeholder='No linked ICDB pinout', parent=None):
        super().__init__(parent)
        self._placeholder = placeholder
        self._source = None
        self._auto_fit = True
        self._zoom = 1.0
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._item = QGraphicsPixmapItem()
        self._item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self._scene.addItem(self._item)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMinimumHeight(150)
        self.setToolTip('Mouse wheel: zoom | Drag: pan | Double-click: fit')

    def _match_pixmap_background(self, pixmap):
        """Use the rendered diagram's corner colour for the letterbox area."""
        image = pixmap.toImage()
        if image.isNull():
            return
        # Use corner sample; all ICDB diagrams have a solid background.
        color = image.pixelColor(0, 0)
        self.setBackgroundBrush(color)
        self._scene.setBackgroundBrush(color)

    def set_source(self, pixmap):
        if pixmap is None or pixmap.isNull():
            self._source = None
            self._item.setPixmap(QPixmap())
            self._scene.setSceneRect(QRectF())
            self.resetTransform()
            self._auto_fit = True
            return
        self._source = pixmap
        self._match_pixmap_background(pixmap)
        self._item.setPixmap(pixmap)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        self.fit_image()

    def fit_image(self):
        self._auto_fit = True
        self._zoom = 1.0
        if self._source is not None and not self._source.isNull():
            self.resetTransform()
            self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, event):
        if self._source is None:
            event.ignore()
            return
        delta = event.angleDelta().y()
        factor = 1.2 if delta > 0 else 1/1.2
        if delta == 0 or not (0.15 <= self._zoom * factor <= 30.0):
            event.accept()
            return
        self._auto_fit = False
        self._zoom *= factor
        self.scale(factor, factor)
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.fit_image()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._auto_fit:
            self.fit_image()
