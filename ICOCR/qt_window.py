"""ICOCR PySide6 main window.

Uses the ICOCR camera, OCR/body-scan, matching, ICDB and reference engines
unchanged. Camera frames are prepared by ``qt_preview.PreviewWorker``; this
module only displays them and never processes video on the GUI thread.
"""
import sys
import time
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QApplication, QMessageBox, QDialog,
    QMainWindow)

from documentation import Documentation
from logic_diagrams import DiagramLibrary
from project_paths import DATA
from qt_recognition_overlay import RecognitionOverlay
from qt_session_history import ReadingHistory
from qt_theme import (apply_palette, normalized_theme, is_dark,
                      viewport_background, use_dark_windows_titlebar)
from qt_user_preferences import Preferences
from shared_data import database_file, save_directory
from version import VERSION
from user_paths import capture_directory as configured_capture_directory
from ui.settings_dialog import SettingsDialog
from ui.workers import DatabaseLoader, EngineLoader
from ui.app_paths import default_package_model
from ui.camera import CameraMixin
from ui.main_layout import MainLayoutMixin
from ui.history_panel import HistoryMixin
from ui.pinout_panel import PinoutPanelMixin
from ui.scanning import ScanMixin

LIVE_INTERVAL_MS = 1600


class MainWindow(MainLayoutMixin, CameraMixin, ScanMixin, PinoutPanelMixin, HistoryMixin, QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f'ICOCR {VERSION}')
        self.resize(1380, 850)
        # Camera and displayed images.
        self.capture = None
        self.preview = None             # PreviewWorker of the running camera
        self._retired = []
        self.frame = None               # newest camera frame
        self.frozen = None              # frame held by Freeze
        self.current_image = None       # frame or opened image currently displayed
        # Recognition overlay. An "epoch" identifies one scan and its frame.
        self.overlay_enabled = True
        self._epoch = 0
        self._shown = None              # dict(epoch, frame) of the displayed overlay
        self._pending = None            # dict(epoch, frame, roi, live) of the running scan
        self._live_matrices = {}        # epoch -> scan frame -> newest frame affine
        self._frozen_matrix = None
        # Scanning and results.
        self.ocr_worker = None
        self.catalog = None
        self.library = None
        self.decision = None
        self.diagnostics = {}
        self.diagnostics_enabled = None
        self._diagnostic_dirty = True
        self._diagnostic_error = None
        self._diagnostic_scheduled = False
        self.display_rows = []
        self.manual_chosen_row = None
        self.reference_choices = []
        self.reference_remembered = {}
        self.package_text = 'Package: not scanned'
        self._pinout_source = None
        self._pinout_cache = {}
        # Settings.
        self.multi_enabled = False
        self.peak_colour = 'Red'
        self.peak_sensitivity = 'Medium'
        self.peak_opacity = '75%'
        self.body_enabled = True
        self.body_only_enabled = False
        self.fast_enabled = True
        self.targeted_enabled = True
        self.package_enabled = True
        self.package_model = None
        self.body_model = str((Path(__file__).parent / 'models' / 'ic_body_segment.onnx').resolve())
        self.theme = 'dark'
        self.invert_svg_pinouts = True
        self.preferences = Preferences(DATA / 'qt_preferences.json')
        self.models_directory = DATA / 'models'
        self.history_model = ReadingHistory()
        self._closing = False
        self._close_finalized = False
        self._queued_scan = False
        self.sleep_enabled = True
        self.sleep_seconds = 120
        self._idle_reference = None
        self._idle_last_change = time.monotonic()
        self._ocr_sleeping = False

        self.documenter = Documentation(DATA, capture_directory=configured_capture_directory(self.preferences.load()))
        self._build()
        self.recognition_overlay = RecognitionOverlay(self.view)
        self.view.view_changed.connect(self.recognition_overlay.place_labels)
        self.view.body_hit_tester = self.recognition_overlay.hit_body
        self.view.body_clicked.connect(self._body_selected)
        self._restore_preferences(self.preferences.load())
        self._apply_theme()
        self.refresh_cameras()

        self.library = DiagramLibrary(background=True)
        self.database_loader = DatabaseLoader(self)
        self.database_loader.loaded.connect(self._database_loaded)
        self.database_loader.finished.connect(self._finish_close_if_ready)
        self.database_loader.start()
        self.engine_loader = EngineLoader(self)
        self.ocr_processor = 'loading…'
        self.engine_loader.failed.connect(self._engine_failed)
        self.engine_loader.loaded.connect(self._engine_loaded)
        self.engine_loader.finished.connect(self._finish_close_if_ready)
        self.engine_loader.start()

        self.live_timer = QTimer(self)
        self.live_timer.timeout.connect(self._live_scan)
        self.live_timer.start(LIVE_INTERVAL_MS)
        # Background writers report through queues; nothing here touches video.
        self.housekeeping = QTimer(self)
        self.housekeeping.timeout.connect(self._drain_events)
        self.housekeeping.start(250)

    def _toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def _leave_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()

    # -- settings --------------------------------------------------------------
    def open_settings(self):
        settings = SettingsDialog(self)
        try:
            if settings.exec() == QDialog.DialogCode.Accepted:
                self._apply_settings(settings)
        finally:
            settings.deleteLater()

    def _apply_settings(self, settings):
        # Validate before applying any settings; do not silently create a new, empty ICDB.
        candidate_data = Path(settings.data_path.text().strip()).expanduser()
        candidate_photos = Path(settings.capture_path.text().strip()).expanduser()
        candidate_models = Path(settings.models_path.text().strip()).expanduser()
        candidate_package = Path(settings.package_path.text().strip()).expanduser()
        candidate_body = Path(settings.body_model_path.text().strip()).expanduser()
        if not all((candidate_data.is_absolute(), candidate_photos.is_absolute(),
                    candidate_models.is_absolute(), candidate_package.is_absolute(), candidate_body.is_absolute())):
            QMessageBox.warning(self, 'Invalid paths', 'All five paths must be absolute.')
            return
        candidate_data = candidate_data.resolve()
        if candidate_data != DATA and not database_file(candidate_data).is_file():
            QMessageBox.warning(self, 'Missing ICDB database',
                f'No ICDB database was found in {candidate_data}. Choose the shared DATA folder '
                'that contains db\\components.sqlite.')
            return
        if not candidate_models.is_dir():
            QMessageBox.warning(self, 'Models folder missing', 'Choose an existing models folder.')
            return
        previous_package = Path(self.effective_package_model()).resolve()
        if candidate_package.resolve() != previous_package:
            if not candidate_package.is_file():
                QMessageBox.warning(self, 'Package model missing', 'Choose an existing ONNX package classifier file.')
                return
            try:
                from package_classifier import contract
                contract(candidate_package)
            except Exception as exc:
                QMessageBox.warning(self, 'Invalid package model', str(exc))
                return
        if not candidate_body.is_file() or candidate_body.suffix.lower() != '.onnx':
            QMessageBox.warning(self, 'Missing body detector', 'Select an existing IC body ONNX segmentation model.')
            return
        if candidate_data != DATA:
            try:
                save_directory(candidate_data)
            except OSError as exc:
                QMessageBox.warning(self, 'Cannot save DATA location', str(exc))
                return
        self.documenter.capture_directory = candidate_photos.resolve()
        self.models_directory = candidate_models.resolve()
        self.body_model = str(candidate_body.resolve())
        if candidate_data != DATA:
            QMessageBox.information(self, 'Restart required',
                'Shared DATA location saved. Restart ICOCR to load the new database and associated paths.')
        self.modes.setCurrentText(settings.mode.currentText())
        self.backend.setCurrentText(settings.backend.currentText())
        self.theme = settings.theme.currentData()
        self.invert_svg_pinouts = settings.invert_svg.isChecked()
        self._pinout_cache.clear()
        self._apply_theme()
        self.peak_colour = settings.peaking_colour.currentText()
        self.peak_sensitivity = settings.sensitivity.currentText()
        self.peak_opacity = settings.opacity.currentText()
        self.body_enabled = settings.auto_body.isChecked()
        self.body_only_enabled = settings.body_only.isChecked()
        self._set_diagnostics_enabled(settings.diagnostics.isChecked())
        self.fast_enabled = settings.fast.isChecked()
        self.targeted_enabled = settings.targeted.isChecked()
        self.package_enabled = settings.package.isChecked()
        # None = follow the Models folder (or the bundled model when it has none).
        self.package_model = (None if candidate_package.resolve() == default_package_model(self.models_directory).resolve()
                              else str(candidate_package.resolve()))
        self.live_recognition.setChecked(settings.live.isChecked())
        self.sleep_enabled = settings.sleep_enabled.isChecked()
        self.sleep_seconds = settings.sleep_seconds.value()
        self._reset_idle_sleep()
        self.multi_enabled = bool(settings.scan_mode.currentData())
        self.show_all.setChecked(settings.show_all.isChecked())
        self.overlay_enabled = settings.show_overlay.isChecked()
        self._save_preferences()
        if candidate_data != DATA:
            # Future launches load preferences from the new DATA root.
            Preferences(candidate_data / 'qt_preferences.json').save(self.preferences.load())
        self.refresh_preview()

    def effective_package_model(self):
        return Path(self.package_model) if self.package_model else default_package_model(self.models_directory)

    def _restore_preferences(self, settings):
        self.icdb_installation = str(settings.get('icdb_installation') or '')
        self.theme = normalized_theme(settings.get('theme', 'dark'))
        self.invert_svg_pinouts = bool(settings.get('invert_svg_pinouts', True))
        self.body_only_enabled = bool(settings.get('body_only_enabled', False))
        self._set_diagnostics_enabled(bool(settings.get('diagnostics_enabled', False)))
        self.overlay_enabled = bool(settings.get('overlay_enabled', True))
        self.sleep_enabled = bool(settings.get('sleep_enabled', True))
        try:
            self.sleep_seconds = max(10, min(3600, int(settings.get('sleep_seconds', 120))))
        except (ValueError, TypeError):
            self.sleep_seconds = 120
        if isinstance(settings.get('models_directory'), str) and settings['models_directory']:
            self.models_directory = Path(settings['models_directory'])
        for key in ('peak_colour', 'peak_sensitivity', 'peak_opacity', 'body_enabled',
                    'fast_enabled', 'targeted_enabled', 'package_enabled'):
            if key in settings and isinstance(settings[key], type(getattr(self, key))):
                setattr(self, key, settings[key])
        # package_model is None (bundled default) or a path string.
        if isinstance(settings.get('body_model'), str) and settings['body_model']:
            self.body_model = settings['body_model']
        if isinstance(settings.get('package_model'), str) and settings['package_model']:
            self.package_model = settings['package_model']
        if settings.get('camera_mode'):
            self.modes.setCurrentText(settings['camera_mode'])
        if settings.get('camera_backend'):
            self.backend.setCurrentText(settings['camera_backend'])
        self.peaking_btn.setChecked(bool(settings.get('peaking_enabled', False)))
        self.live_recognition.setChecked(bool(settings.get('live_recognition', False)))
        self.multi_enabled = bool(settings.get('multi_enabled', False))
        self.show_all.setChecked(bool(settings.get('show_all', False)))
        dims = settings.get('window_size')
        if isinstance(dims, list) and len(dims) == 2 and all(isinstance(v, int) for v in dims):
            self.resize(max(940, dims[0]), max(600, dims[1]))
        widths = settings.get('workspace_sizes')
        if isinstance(widths, list) and len(widths) == 2 and all(isinstance(v, int) and v > 0 for v in widths):
            self.workspace.setSizes(widths)

    def _save_preferences(self):
        values = {key: getattr(self, key) for key in (
            'peak_colour', 'peak_sensitivity', 'peak_opacity', 'body_enabled',
            'fast_enabled', 'targeted_enabled', 'package_enabled', 'package_model', 'body_model',
            'body_only_enabled', 'diagnostics_enabled')}
        values.update(theme=self.theme, invert_svg_pinouts=self.invert_svg_pinouts, camera_mode=self.modes.currentText(),
                      camera_backend=self.backend.currentText(),
                      peaking_enabled=self.peaking_btn.isChecked(),
                      live_recognition=self.live_recognition.isChecked(),
                      multi_enabled=self.multi_enabled,
                      show_all=self.show_all.isChecked(),
                      overlay_enabled=self.overlay_enabled,
                      sleep_enabled=self.sleep_enabled,
                      sleep_seconds=self.sleep_seconds,
                      models_directory=str(self.models_directory),
                      capture_folder=str(self.documenter.capture_directory),
                      window_size=[self.width(), self.height()],
                      workspace_sizes=self.workspace.sizes())
        if getattr(self, 'icdb_installation', None):
            values['icdb_installation'] = self.icdb_installation
        elif self.preferences.load().get('icdb_installation'):
            values['icdb_installation'] = self.preferences.load()['icdb_installation']
        self.preferences.save(values)

    def _apply_theme(self):
        app = QApplication.instance()
        app.setStyleSheet('')  # Remove old ICOCR square-edged stylesheet
        apply_palette(app, is_dark(self.theme))
        use_dark_windows_titlebar(self)
        self.view.setBackgroundBrush(QColor(viewport_background(self.theme)))
        if self.reference_choices:
            self._render_reference(self.reference_select.currentIndex())
        if self.history_list.currentRow() >= 0:
            self._history_selected(self.history_list.currentRow())

    # -- database --------------------------------------------------------------
    def reload_database(self):
        if self.database_loader.isRunning():
            return
        if self.library:
            self.library.refresh()
        self._pinout_cache.clear()
        self.database_loader.start()

    def _engine_loaded(self, label):
        self.ocr_processor = label or 'ready'

    def _engine_failed(self, text):
        self.ocr_processor = 'unavailable — ' + text
        self.statusBar().showMessage('OCR engine unavailable: ' + text)

    def _database_loaded(self, catalog, message):
        self.catalog = catalog
        if catalog and getattr(self, '_refresh_alias_results', False):
            self._refresh_alias_results = False
            from component_catalog import annotate
            def refresh(row):
                text = row.get('raw_text') or row.get('text') or row.get('key') or ''
                # A new alias, or a part added in ICDB that this reading now names exactly.
                newly_named = (not row.get('selected_database_match') and
                               any(m.get('match_type') == 'exact' for m in catalog.find(text)))
                if (newly_named or catalog.explicit_marking_matches(text)
                        or catalog.corrected_alias_suggestions(text)):
                    row.update(annotate([row], catalog,
                                        package_prediction=row.get('package_classification'))[0])
                    if row.get('selected_database_match'):
                        row['rejection_reason'] = ''
                        row['provisional'] = False
            for entry in self.history_model.entries:
                refresh(entry['row'])
            for row in self.display_rows:
                refresh(row)
            self._refresh_history()
            self._reading_chosen()
        self.statusBar().showMessage(message)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._fit_visible_pinouts)

    # -- shutdown --------------------------------------------------------------
    def _workers_running(self):
        return ((self.ocr_worker is not None and self.ocr_worker.isRunning()) or
                any(worker.isRunning() for worker in self._retired) or
                self.database_loader.isRunning() or self.engine_loader.isRunning())

    def _finish_close_if_ready(self):
        if self._closing and not self._close_finalized and not self._workers_running():
            # Re-enter closeEvent only after Qt has emitted finished for all workers.
            QTimer.singleShot(0, self.close)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, lambda: use_dark_windows_titlebar(self))

    def closeEvent(self, event):
        if self._close_finalized:
            event.accept()
            return
        if not self._closing:
            self._closing = True
            self.live_timer.stop()
            self.housekeeping.stop()
            self.scan_btn.setEnabled(False)
            self.start_button.setEnabled(False)
            self.settings_button.setEnabled(False)
            try:
                self._save_preferences()
            except OSError as exc:
                self.statusBar().showMessage(f'Could not save preferences: {exc}')
            # Stop video at once, but never destroy a running Qt thread.
            self.stop_camera()
            if self.ocr_worker is not None and self.ocr_worker.isRunning():
                self.ocr_worker.cancel()
        if self._workers_running():
            self.statusBar().showMessage('Closing — waiting for active worker to stop…')
            event.ignore()
            return
        if self.library:
            self.library.close()
            self.library = None
        self.documenter.close(timeout=2.0)
        self._close_finalized = True
        event.accept()


def run():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle('Fusion')
    apply_palette(app, dark=True)
    icon = Path(__file__).resolve().parent / 'ICOCR.ico'
    if icon.is_file():
        from PySide6.QtGui import QIcon
        app.setWindowIcon(QIcon(str(icon)))
    window = MainWindow()
    window.show()
    # Camera always starts on launch. Live OCR follows the saved Recognition setting.
    QTimer.singleShot(100, window.start_camera)
    return app.exec()
