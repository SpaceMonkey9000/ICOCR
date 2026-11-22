"""Qt presentation of recognition geometry. Source images are never modified.

All outlines live under one invisible root item whose coordinates are the
pixels of the scanned frame. Following the scene on live video is a single
``setTransform`` on that root per frame; nothing is rebuilt or re-projected.
Outline pens are cosmetic and labels ignore the view transform, so both keep
their on-screen size at every zoom level.
"""
import math
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPen, QColor, QPolygonF, QFont, QFontMetricsF, QTransform
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPolygonItem, QGraphicsRectItem

BODY_COLOUR = '#4cb7e8'


def point_list(box):
    """Accept OCR quadrilaterals or detector xyxy rectangles in pixel coordinates."""
    if box is None:
        return []
    try:
        if len(box) == 4 and all(isinstance(x, (int, float)) for x in box):
            x1, y1, x2, y2 = map(float, box)
            pts = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        else:
            pts = [(float(p[0]), float(p[1])) for p in box]
        return pts if len(pts) >= 3 and all(math.isfinite(v) for p in pts for v in p) else []
    except (TypeError, ValueError, IndexError):
        return []


def translate_box(box, roi, full_size):
    """Map ROI-local OCR coordinates to original-frame coordinates."""
    pts = point_list(box)
    w, h = full_size
    x0 = int(roi[0]*w)
    y0 = int(roi[1]*h)
    return [(x+x0, y+y0) for x, y in pts]


def affine_to_transform(matrix):
    """2x3 affine [[a, b, tx], [c, d, ty]] as a QTransform."""
    if matrix is None:
        return QTransform()
    return QTransform(float(matrix[0][0]), float(matrix[1][0]),
                      float(matrix[0][1]), float(matrix[1][1]),
                      float(matrix[0][2]), float(matrix[1][2]))


def overlay_text(row, database_loaded):
    """Preserve the test13 identification AND its function description.

    Some OCR scan result variants expose a chosen ICDB entry but omit the
    derived function_summary. Recover only source-listed functions; never
    invent a component function for an uncertain candidate.
    """
    from app_presenters import overlay_label
    from component_catalog import record_description

    effective = row
    if not row.get('function_summary'):
        selected = row.get('selected_database_match') or {}
        description = record_description(selected) if selected else ''
        if description:
            effective = dict(row, function_summary=description)
    full_text, colour = overlay_label(effective, database_loaded)
    title, separator, description = full_text.partition('\n')
    return title.strip(), description.strip() if separator else '', str(colour)


class LabelItem(QGraphicsItem):
    """Fixed-screen-size, two-level OCR tag with a wrapped ICDB description."""
    PAD_X, PAD_Y, GAP, LINE_GAP = 11, 8, 7, 4
    MAX_CONTENT_WIDTH = 460
    MAX_DESCRIPTION_LINES = 2

    def __init__(self, title, description, colour, parent):
        super().__init__(parent)
        self.title = title
        self.description = description
        self.colour = QColor(colour)
        self.title_font = QFont('Segoe UI', 15, QFont.Weight.Bold)
        self.description_font = QFont('Segoe UI', 12, QFont.Weight.Medium)
        self.title_metrics = QFontMetricsF(self.title_font)
        self.description_metrics = QFontMetricsF(self.description_font)
        self._title_line = self.title_metrics.elidedText(
            self.title, Qt.TextElideMode.ElideRight, self.MAX_CONTENT_WIDTH)
        self._description_lines = self._wrap_description(description)
        content_width = max(
            self.title_metrics.horizontalAdvance(self._title_line),
            *(self.description_metrics.horizontalAdvance(line)
              for line in self._description_lines),
            80.0,
        )
        self._width = content_width + 2 * self.PAD_X
        text_height = self.title_metrics.height()
        if self._description_lines:
            text_height += self.LINE_GAP + len(self._description_lines) * self.description_metrics.height()
        self._height = text_height + 2 * self.PAD_Y
        self._below = False
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setZValue(2)

    def _wrap_description(self, description):
        """Wrap on word boundaries to two measured lines; elide overflow."""
        text = ' '.join(str(description or '').split())
        if not text:
            return []
        words = text.split(' ')
        lines = []
        current = ''
        while words and len(lines) < self.MAX_DESCRIPTION_LINES:
            word = words.pop(0)
            proposed = (current + ' ' + word).strip()
            if self.description_metrics.horizontalAdvance(proposed) <= self.MAX_CONTENT_WIDTH:
                current = proposed
                continue
            if current:
                lines.append(current)
                current = ''
                words.insert(0, word)
            else:
                lines.append(self.description_metrics.elidedText(
                    word, Qt.TextElideMode.ElideRight, self.MAX_CONTENT_WIDTH))
        if current and len(lines) < self.MAX_DESCRIPTION_LINES:
            lines.append(current)
        if words:
            last = lines[-1] if lines else ''
            lines[-1] = self.description_metrics.elidedText(
                last + ' ' + ' '.join(words), Qt.TextElideMode.ElideRight,
                self.MAX_CONTENT_WIDTH)
        return lines

    @property
    def height(self):
        return self._height + self.GAP

    def set_below(self, below):
        if below != self._below:
            self.prepareGeometryChange()
            self._below = below

    def _box(self):
        y = self.GAP if self._below else -self._height - self.GAP
        return QRectF(0, y, self._width, self._height)

    def boundingRect(self):
        return self._box().adjusted(-2, -2, 2, 2)

    def paint(self, painter, option, widget=None):
        box = self._box()
        painter.setPen(QPen(self.colour, 1.8))
        painter.setBrush(QColor(12, 20, 27, 239))
        painter.drawRoundedRect(box, 6, 6)
        x = box.left() + self.PAD_X
        y = box.top() + self.PAD_Y + self.title_metrics.ascent()
        painter.setFont(self.title_font)
        painter.setPen(self.colour)
        painter.drawText(QPointF(x, y), self._title_line)
        if self._description_lines:
            y += self.title_metrics.descent() + self.LINE_GAP + self.description_metrics.ascent()
            painter.setFont(self.description_font)
            painter.setPen(QColor('#f0f4f8'))
            for line in self._description_lines:
                painter.drawText(QPointF(x, y), line)
                y += self.description_metrics.height()


class RecognitionOverlay:
    """Outlines and labels of the latest scan, in scan-frame pixel coordinates."""

    def __init__(self, view):
        self.view = view
        self.root = QGraphicsRectItem()
        self.root.setFlag(QGraphicsItem.GraphicsItemFlag.ItemHasNoContents, True)
        self.root.setZValue(22)
        self.root.setVisible(False)
        view.canvas.addItem(self.root)
        self.labels = []          # (LabelItem, anchor QPointF in scan-frame pixels)
        self.body_items = []
        self.count = 0

    def __bool__(self):
        return self.count > 0

    def clear(self):
        for child in self.root.childItems():
            self.view.canvas.removeItem(child)
        self.labels.clear()
        self.body_items.clear()
        self.count = 0
        self.root.setVisible(False)

    def add(self, points, label='', colour=BODY_COLOUR, dashed=False, description=''):
        """One outline (list of (x, y) in scan-frame pixels) with an optional label."""
        if not points:
            return
        polygon = QGraphicsPolygonItem(QPolygonF([QPointF(x, y) for x, y in points]), self.root)
        pen = QPen(QColor(colour), 3.5)
        pen.setCosmetic(True)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        if dashed:
            pen.setStyle(Qt.PenStyle.DashLine)
        polygon.setPen(pen)
        polygon.setBrush(Qt.BrushStyle.NoBrush)
        self.count += 1
        if dashed:
            self.body_items.append(polygon)
        if label:
            anchor = QPointF(min(p[0] for p in points), min(p[1] for p in points))
            item = LabelItem(label, description, colour, self.root)
            item.setPos(anchor)
            self.labels.append((item, anchor))

    def set_results(self, rows, body_boxes, roi, source_size, database_loaded=True):
        """Replace the overlay with OCR rows and body outlines of one scan.

        Boxes are relative to the scanned selection; ``roi`` and ``source_size``
        (w, h of the scanned frame) place them in frame coordinates.
        """
        self.clear()
        for box in body_boxes:
            self.add(translate_box(box, roi, source_size), dashed=True)
        for row in rows:
            points = translate_box(row.get('box'), roi, source_size)
            if not points:
                continue
            title, description, colour = overlay_text(row, database_loaded)
            self.add(points, title, colour, description=description)

    def hit_body(self, scene_point, source_size):
        """Return the selected body's *display-frame* normalized rectangle.

        Item mapping incorporates the current motion transform, so clicking
        a moving live component does not reuse stale scanned-frame coordinates.
        """
        if not self.root.isVisible():
            return None
        w, h = source_size
        if w <= 0 or h <= 0:
            return None
        for item in reversed(self.body_items):
            local = item.mapFromScene(scene_point)
            if not item.polygon().containsPoint(local, Qt.FillRule.OddEvenFill):
                continue
            poly = item.mapToScene(item.polygon())
            bounds = poly.boundingRect()
            x1 = max(0., min(1., bounds.left()/w))
            y1 = max(0., min(1., bounds.top()/h))
            x2 = max(0., min(1., bounds.right()/w))
            y2 = max(0., min(1., bounds.bottom()/h))
            if (x2-x1)*w >= 12 and (y2-y1)*h >= 12:
                return (x1, y1, x2, y2)
        return None

    def draw(self, matrix=None, visible=True):
        """Show the overlay moved by ``matrix`` (scan frame -> displayed frame;
        None = identity), or hide it."""
        if not visible or not self.count:
            self.root.setVisible(False)
            return
        self.root.setTransform(affine_to_transform(matrix))
        self.root.setVisible(True)
        self.place_labels()

    def place_labels(self):
        """Flip a label below its anchor when it would leave the top of the image."""
        if not self.labels or not self.root.isVisible():
            return
        top = self.view.mapFromScene(QPointF(0, 0)).y()
        for item, anchor in self.labels:
            y = self.view.mapFromScene(self.root.mapToScene(anchor)).y()
            item.set_below(y - item.height < max(0, top))
