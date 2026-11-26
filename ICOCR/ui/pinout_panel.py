"""Pinout reference shown for the selected reading on the Identify tab."""
from pathlib import Path
from PySide6.QtGui import QPixmap
from logic_diagrams import reference_labels
from package_pinouts import select_reference
from qt_theme import (is_dark)
from reference_images import load_reference_image


PINOUT_CACHE_SIZE = 12


class PinoutPanelMixin:
    """Identify-tab pinout lookup, rendering and fitting. Mixed into MainWindow."""

    def _pinout_for(self, row):
        self.diagnostics["pinout_diagnostic"] = {"status": "No database match or pinout library"}
        self.reference_choices = []
        self.reference_select.blockSignals(True)
        self.reference_select.clear()
        match = row.get('selected_database_match') or {}
        if match and self.library:
            try:
                self.reference_choices = self.library.choices(row)
                self.reference_select.addItems(reference_labels(self.reference_choices))
                selected, report = select_reference(
                    self.reference_choices, match.get('package', ''),
                    self.reference_remembered.get((match.get('part'), match.get('manufacturer'))),
                    self.diagnostics.get('package_classification'))
                if selected:
                    self.reference_select.setCurrentIndex(self.reference_choices.index(selected))
                self.pinout_note.setText(report.get('reason', ''))
                self.diagnostics['pinout_diagnostic'] = dict(status='selected' if selected else 'no reference selected', reason=report.get('reason'), choices=[dict(reference_id=c.get('reference_id'), path=str(c.get('path')), package=c.get('package')) for c in self.reference_choices], selected_reference=selected.get('reference_id') if selected else None)
            except Exception as exc:
                self.pinout_note.setText('Pinout lookup error: ' + str(exc))
                self.diagnostics['pinout_diagnostic'] = dict(status='lookup error', error=str(exc))
        self.reference_select.blockSignals(False)
        self.pinout_title.setText(match.get('part') or row.get('key', 'No component'))
        self._render_reference(self.reference_select.currentIndex())

    def _remember_reference(self, index):
        if not 0 <= index < len(self.reference_choices):
            return
        current = self.results.currentRow()
        if not 0 <= current < len(self.display_rows):
            return
        match = self.display_rows[current].get('selected_database_match') or {}
        if match:
            self.reference_remembered[(match.get('part'), match.get('manufacturer'))] = \
                self.reference_choices[index].get('reference_id')

    def _reference_pixmap(self, path):
        """Shared theme-aware ICDB pinout loader for Identify and History."""
        path = Path(path)
        key = (str(path), self.theme, self.invert_svg_pinouts)
        pixmap = self._pinout_cache.get(key)
        if pixmap is None:
            from PIL.ImageQt import ImageQt
            image = load_reference_image(path, (1400, 1400))
            if is_dark(self.theme) and self.invert_svg_pinouts and path.suffix.lower() == '.svg':
                from PIL import ImageOps
                image = ImageOps.invert(image.convert('RGB'))
            pixmap = QPixmap.fromImage(ImageQt(image))
            if len(self._pinout_cache) >= PINOUT_CACHE_SIZE:
                self._pinout_cache.pop(next(iter(self._pinout_cache)))
            self._pinout_cache[key] = pixmap
        return pixmap

    def _render_reference(self, index):
        if not 0 <= index < len(self.reference_choices):
            self._pinout_source = None
            self.pinout_image.set_source(None)
            return
        try:
            pixmap = self._reference_pixmap(self.reference_choices[index]['path'])
            if pixmap is not self._pinout_source:
                self._pinout_source = pixmap
                self._fit_pinout_pixmap()
        except Exception as exc:
            self._pinout_source = None
            self.pinout_image.set_source(None)
            self.pinout_note.setText('Cannot render pinout: ' + str(exc))
            self.diagnostics.setdefault('pinout_diagnostic', {}).update(status='render error', error=str(exc))

    def _fit_visible_pinouts(self):
        # Preserve manual zoom/pan when changing tabs or resizing the window.
        if self.pinout_image._auto_fit:
            self.pinout_image.fit_image()
        if self.history_pinout_image._auto_fit:
            self.history_pinout_image.fit_image()

    def _fit_pinout_pixmap(self):
        if self._pinout_source is not None:
            self.pinout_image.set_source(self._pinout_source)
