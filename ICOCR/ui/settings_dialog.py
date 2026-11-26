"""Settings dialog: camera, recognition, rules, data and tools tabs."""
from contextlib import closing
import os
import sqlite3
import sys
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QCheckBox, QListWidget,
    QTabWidget, QFileDialog, QMessageBox, QFormLayout, QDialog, QGroupBox,
    QDialogButtonBox, QListWidgetItem,
    QLineEdit, QSpinBox)
from config_loader import RULES, _LEGACY_DATA, validate
from project_paths import DATA
from shared_data import database_file
from qt_theme import (THEMES, use_dark_windows_titlebar)
from rule_modules import RuleSnapshot, rules_directory, save_enabled


def database_information(path):
    """Read ICDB's committed version and counts without modifying shared DATA."""
    unavailable = 'Unavailable'
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=0.25)) as db:
            db.execute('BEGIN')
            tables = {name for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'components' not in tables:
                return (unavailable,) * 3
            devices = db.execute('SELECT COUNT(*) FROM components').fetchone()[0]
            version = 'Unversioned'
            if 'icdb_database_version' in tables:
                row = db.execute('SELECT base, revision FROM icdb_database_version WHERE id=1').fetchone()
                if row:
                    base, revision = row
                    version = base + (f'-r{revision}' if revision else '')
            pinouts = unavailable
            if 'pl_definitions' in tables:
                count = db.execute('SELECT COUNT(*) FROM pl_definitions').fetchone()[0]
                pinouts = f'{count:,}'
            return version, f'{devices:,}', pinouts
    except (OSError, sqlite3.Error):
        return (unavailable,) * 3


class SettingsDialog(QDialog):
    """One settings surface. Changes are applied by the window on acceptance."""
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle('ICOCR — Settings')
        self.resize(740, 520)
        self.setMinimumSize(620, 420)
        root = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)
        root.addWidget(self.tabs, 1)

        camera = QWidget()
        cam = QFormLayout(camera)
        self.mode = QComboBox()
        self.mode.addItems([window.modes.itemText(i) for i in range(window.modes.count())])
        self.mode.setCurrentText(window.modes.currentText())
        cam.addRow('Video mode', self.mode)
        self.backend = QComboBox()
        self.backend.addItems([window.backend.itemText(i) for i in range(window.backend.count())])
        self.backend.setCurrentText(window.backend.currentText())
        cam.addRow('Capture backend', self.backend)
        refresh = QPushButton('Refresh camera list')
        refresh.clicked.connect(window.refresh_cameras)
        cam.addRow('', refresh)
        self.peaking_colour = QComboBox()
        self.peaking_colour.addItems(['Red', 'Green', 'Yellow', 'Cyan'])
        self.peaking_colour.setCurrentText(window.peak_colour)
        cam.addRow('Peaking colour', self.peaking_colour)
        self.sensitivity = QComboBox()
        self.sensitivity.addItems(['Low', 'Medium', 'High'])
        self.sensitivity.setCurrentText(window.peak_sensitivity)
        cam.addRow('Peaking sensitivity', self.sensitivity)
        self.opacity = QComboBox()
        self.opacity.addItems(['50%', '75%', '100%'])
        self.opacity.setCurrentText(window.peak_opacity)
        cam.addRow('Peaking opacity', self.opacity)
        notice = QLabel('Changing video mode or backend takes effect the next time the camera starts.')
        notice.setWordWrap(True)
        cam.addRow('', notice)
        self.tabs.addTab(camera, 'Camera settings')

        recognition = QWidget()
        rec = QVBoxLayout(recognition)
        scan_scope = QHBoxLayout()
        scan_scope.addWidget(QLabel('Scan mode'))
        self.scan_mode = QComboBox()
        self.scan_mode.addItem('Single chip', False)
        self.scan_mode.addItem('Multiple chips', True)
        self.scan_mode.setCurrentIndex(1 if window.multi_enabled else 0)
        self.scan_mode.setToolTip('Single: recognise one body in the selected region. Multiple: scan each detected body. Applies to manual and live scans.')
        scan_scope.addWidget(self.scan_mode)
        scan_scope.addStretch(1)
        rec.addLayout(scan_scope)
        self.live = QCheckBox('Live recognition')
        self.live.setChecked(window.live_recognition.isChecked())
        rec.addWidget(self.live)
        self.sleep_enabled = QCheckBox('Sleep live OCR when the scene is unchanged')
        self.sleep_enabled.setChecked(window.sleep_enabled)
        rec.addWidget(self.sleep_enabled)
        sleep_row = QHBoxLayout()
        sleep_row.addWidget(QLabel('Idle time before sleep (seconds)'))
        self.sleep_seconds = QSpinBox()
        self.sleep_seconds.setRange(10, 3600)
        self.sleep_seconds.setValue(window.sleep_seconds)
        self.sleep_seconds.setSuffix(' s')
        sleep_row.addWidget(self.sleep_seconds)
        sleep_row.addStretch(1)
        rec.addLayout(sleep_row)
        rec.addWidget(QLabel('Camera preview continues. Recognition resumes when the scene changes.'))
        self.body_only = QCheckBox('Prototype: OCR only inside detected IC bodies')
        self.body_only.setToolTip('Skips whole-frame OCR discovery; requires the ONNX body detector. No detected bodies means no OCR.')
        self.body_only.setChecked(window.body_only_enabled)
        rec.addWidget(self.body_only)
        self.auto_body = QCheckBox('Detect component body before OCR')
        self.auto_body.setChecked(window.body_enabled)
        rec.addWidget(self.auto_body)
        self.fast = QCheckBox('Fast scan')
        self.fast.setChecked(window.fast_enabled)
        rec.addWidget(self.fast)
        self.targeted = QCheckBox('Targeted original')
        self.targeted.setChecked(window.targeted_enabled)
        rec.addWidget(self.targeted)
        self.package = QCheckBox('Package classification')
        self.package.setChecked(window.package_enabled)
        rec.addWidget(self.package)
        self.show_all = QCheckBox('Show excluded readings')
        self.show_all.setChecked(window.show_all.isChecked())
        rec.addWidget(self.show_all)
        self.show_overlay = QCheckBox('Display recognition outlines and labels on preview')
        self.show_overlay.setChecked(window.overlay_enabled)
        rec.addWidget(self.show_overlay)
        self.diagnostics = QCheckBox('Enable scan diagnostics')
        self.diagnostics.setChecked(window.diagnostics_enabled)
        self.diagnostics.setToolTip('Record detailed recognition evidence for subsequent scans. Disable for normal operation.')
        rec.addWidget(self.diagnostics)
        rec.addStretch(1)
        self.tabs.addTab(recognition, 'Recognition')

        rules = QWidget()
        rl = QVBoxLayout(rules)
        rl.addWidget(QLabel('Enable or disable recognition rules. Restart ICOCR after saving.'))
        self.rules_filter = QLineEdit()
        self.rules_filter.setPlaceholderText('Filter recognition rules')
        rl.addWidget(self.rules_filter)
        self.rules_list = QListWidget()
        rl.addWidget(self.rules_list, 1)
        self.rules_info = QLabel()
        self.rules_info.setWordWrap(True)
        rl.addWidget(self.rules_info)
        rules_buttons = QHBoxLayout()
        refresh_rules = QPushButton('Refresh')
        refresh_rules.clicked.connect(self._load_rules)
        rules_buttons.addWidget(refresh_rules)
        save_rules = QPushButton('Save rules')
        save_rules.clicked.connect(self._save_rules)
        rules_buttons.addWidget(save_rules)
        rl.addLayout(rules_buttons)
        self.rules_filter.textChanged.connect(self._filter_rules)
        self._load_rules()
        self.tabs.addTab(rules, 'Rules')

        data = QWidget()
        dl = QVBoxLayout(data)
        forms = QFormLayout()
        self.data_path = QLineEdit(str(DATA))
        self.capture_path = QLineEdit(str(window.documenter.capture_directory))
        self.models_path = QLineEdit(str(window.models_directory))
        self.package_path = QLineEdit(str(window.effective_package_model()))
        self.body_model_path = QLineEdit(str(window.body_model or ''))
        for title, field, mode in (
            ('Shared DATA folder', self.data_path, 'directory'),
            ('Saved photos', self.capture_path, 'directory'),
            ('Models folder', self.models_path, 'directory'),
            ('Package model', self.package_path, 'model'),
            ('Body segmentation model', self.body_model_path, 'model'),
        ):
            holder = QWidget()
            line = QHBoxLayout(holder)
            line.setContentsMargins(0, 0, 0, 0)
            line.addWidget(field, 1)
            button = QPushButton('Browse')
            button.clicked.connect(lambda _, f=field, m=mode: self._choose_path(f, m))
            line.addWidget(button)
            forms.addRow(title, holder)
        dl.addLayout(forms)
        database_info = QGroupBox('Database information')
        info_form = QFormLayout(database_info)
        catalog = getattr(window, 'catalog', None)
        path = catalog.path if catalog is not None else database_file(DATA)
        values = database_information(path)
        for label, value in zip(('Database version', 'Devices', 'Pinout definitions'), values):
            field = QLabel(value)
            field.setTextFormat(Qt.TextFormat.PlainText)
            info_form.addRow(label, field)
        dl.addWidget(database_info)
        dl.addStretch(1)
        self.tabs.addTab(data, 'Data and documentation')

        tools = QWidget()
        tl = QVBoxLayout(tools)
        appearance = QFormLayout()
        self.theme = QComboBox()
        for key, label in THEMES.items():
            self.theme.addItem(label, key)
        self.theme.setCurrentIndex(max(0, self.theme.findData(window.theme)))
        appearance.addRow('Appearance', self.theme)
        self.invert_svg = QCheckBox('Invert SVG pinouts in dark mode')
        self.invert_svg.setChecked(window.invert_svg_pinouts)
        appearance.addRow('Pinout images', self.invert_svg)
        tl.addLayout(appearance)
        processor = QLabel('OCR processor: ' + str(getattr(window, 'ocr_processor', '')))
        processor.setWordWrap(True)
        tl.addWidget(processor)
        reload_button = QPushButton('Reload database')
        reload_button.clicked.connect(lambda: (window.reload_database(), window.statusBar().showMessage('Database reload requested')))
        tl.addWidget(reload_button)
        open_data = QPushButton('Open data folder')
        def browse_data():
            if sys.platform == 'win32':
                os.startfile(str(DATA))
            else:
                QMessageBox.information(self, 'Data folder', str(DATA))
        open_data.clicked.connect(browse_data)
        tl.addWidget(open_data)
        tl.addStretch(1)
        self.tabs.addTab(tools, 'Tools')

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, lambda: use_dark_windows_titlebar(self))

    def _choose_path(self, field, mode):
        current = field.text().strip()
        if mode == 'model':
            path, _ = QFileDialog.getOpenFileName(self, 'Choose ONNX model', current, 'ONNX (*.onnx)')
        else:
            path = QFileDialog.getExistingDirectory(self, 'Choose folder', current)
        if path:
            field.setText(path)

    def _load_rules(self):
        try:
            self.rules_snapshot = RuleSnapshot(rules_directory(), _LEGACY_DATA, validate)
            self.rules_list.clear()
            for row in sorted(self.rules_snapshot.modules, key=lambda r: (r['category'], r['name'], r['id'])):
                item = QListWidgetItem(f"{row['category']}  /  {row['name']}")
                item.setData(Qt.ItemDataRole.UserRole, row['id'])
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if row['enabled'] else Qt.CheckState.Unchecked)
                self.rules_list.addItem(item)
            self.rules_info.setText(f"{len(self.rules_snapshot.modules)} rules; "
                f"{len(self.rules_snapshot.errors)} invalid files. "
                + ('Saved configuration differs from running rules; restart required.'
                   if self.rules_snapshot.sha256 != RULES.sha256 else ''))
            self._filter_rules(self.rules_filter.text())
        except Exception as exc:
            self.rules_info.setText(f'Cannot load rules: {exc}')

    def _filter_rules(self, query):
        query = query.strip().casefold()
        for i in range(self.rules_list.count()):
            item = self.rules_list.item(i)
            item.setHidden(bool(query and query not in item.text().casefold()))

    def _save_rules(self):
        if not hasattr(self, 'rules_snapshot'):
            return
        values = {self.rules_list.item(i).data(Qt.ItemDataRole.UserRole):
                  self.rules_list.item(i).checkState() == Qt.CheckState.Checked
                  for i in range(self.rules_list.count())}
        try:
            count = save_enabled(self.rules_snapshot.modules, values, validate, _LEGACY_DATA)
        except (OSError, ValueError, KeyError) as exc:
            QMessageBox.warning(self, 'Rules not saved', str(exc))
            return
        self._load_rules()
        self.rules_info.setText(f'{count} rule change(s) saved. Restart ICOCR to apply.')
