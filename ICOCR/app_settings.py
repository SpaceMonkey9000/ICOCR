"""Persisted preferences, Settings actions and option toggles."""
import json
import logging
import os
import time
from pathlib import Path
from tkinter import filedialog, messagebox

from config_loader import configuration_diagnostics
from ic_detector import DetectionWorker
from ic_preprocessing import configuration
from project_paths import DATA
from user_paths import CONFIG_DIR, SETTINGS_FILE
from ui_regions import REGIONS, region_from_preferences

MODELS = DATA/'models'
# Boolean settings saved in ui_settings.json (Tk variable names).
SAVED_FLAGS = ('sleep_enabled', 'mjpg', 'auto_body', 'detector_body', 'fast_scan', 'targeted_original',
               'detector_alignment', 'show_all', 'show_detections', 'observation_live', 'multi_chip',
               'logging_enabled', 'scan_verification')
SAVED_CHOICES = ('backend', 'mode')        # read-only comboboxes
OBSOLETE_SETTINGS = ('diagram_folder', 'reference_source')


def load_json(path, expected=dict, label='settings'):
    """Parsed JSON of the expected type, or None (missing files are not an error)."""
    try:
        value = json.loads(Path(path).read_text('utf-8'))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        logging.exception('Could not read %s: %s', label, path)
        return None
    if not isinstance(value, expected):
        logging.warning('Ignored %s: %s does not contain a %s', label, path, expected.__name__)
        return None
    return value


def write_json_atomic(path, value):
    """Write beside the target, then replace it: a failed write never leaves half a file."""
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2), 'utf-8')
    temporary.replace(path)


def save_preprocessing(path, config):
    """Standard (None) removes preprocessing.json; writing null logged a warning
    on every start (0.8.8). Other policies are written atomically."""
    if config is None:
        Path(path).unlink(missing_ok=True)
    else:
        write_json_atomic(path, config)


def read_settings_section(section):
    payload = load_json(SETTINGS_FILE, dict, 'application settings') or {}
    return payload.get(section)


def write_settings_section(section, value):
    payload = load_json(SETTINGS_FILE, dict, 'application settings') or {'schema_version': 1}
    if payload.get('schema_version') != 1:
        raise ValueError('unsupported application settings schema')
    payload[section] = value
    write_json_atomic(SETTINGS_FILE, payload)


def model_setting(model_path, models=MODELS):
    """ui_settings.json value for a detector model: path relative to DATA/models, or None."""
    if not model_path:
        return None
    try:
        return Path(model_path).resolve().relative_to(Path(models).resolve()).as_posix()
    except ValueError:
        logging.warning('Detector model outside %s is not remembered: %s', models, model_path)
        return None


def saved_model(name, models=MODELS):
    """Resolved model file for a saved setting, or None when missing/outside DATA/models."""
    if not name or Path(name).is_absolute():
        return None
    models = Path(models).resolve()
    path = (models/name).resolve()
    return path if path.is_relative_to(models) and path.is_file() else None


class SettingsMixin:
    @staticmethod
    def requested_device():
        return os.environ.get('ICLENS_DEVICE', 'auto')

    def load_preprocessing(self):
        values = read_settings_section('preprocessing')
        if values is None:
            return None
        try:
            return configuration(values)
        except (ValueError, TypeError, KeyError):
            logging.exception('Invalid snapshot preprocessing settings; using Standard')
            return None

    def choose_data_folder(self):
        from shared_data import choose_directory
        choose_directory(self.root, DATA)

    def change_input_region(self, event=None):
        index = REGIONS.index(self.ocr_input_region.get())
        self.auto_body.set(index != 0)
        self.detector_body.set(index == 2)
        if event is not None:
            self.invalidate('OCR input region changed — scan again')

    def open_settings(self):
        self.settings_window.deiconify()
        self.settings_window.lift()

    def hide_settings(self):
        try:
            self.save_settings()
        finally:
            self.settings_window.withdraw()

    def restore_settings(self):
        preferences = self.ui_preferences
        self.sleep_seconds.set(str(preferences.get("sleep_seconds", 120)))
        self.sleep_seconds.set(str(self.sleep_timeout()))
        for name in SAVED_CHOICES:
            control = getattr(self, name)
            if preferences.get(name) in control['values']:
                control.set(preferences[name])
        for name in SAVED_FLAGS:
            if isinstance(preferences.get(name), bool):
                getattr(self, name).set(preferences[name])
        self.ocr_input_region.set(region_from_preferences(preferences))
        self.change_input_region()
        self.show_logic_diagrams.set(preferences.get('show_logic_diagrams', True) is not False)
        self.diagram_panel.visible(self.show_logic_diagrams.get())
        self.fast_mode = self.fast_scan.get()
        self.observation_mode = self.observation_live.get()
        self.multi_mode = self.multi_chip.get()
        self.targeted_original_mode = self.targeted_original.get()
        self.detector_alignment_mode = self.detector_alignment.get()
        path = saved_model(preferences.get('detector_model'))
        if path is not None:
            self.use_detector_model(path)
        if self.show_detections.get():
            self.toggle_detector()

    def save_settings(self):
        """Write UI preferences to settings.json; never raises on window close."""
        try:
            values = dict(self.ui_preferences)
            values.update({name: getattr(self, name).get() for name in SAVED_CHOICES + SAVED_FLAGS})
            values.update(settings_version=3, sleep_seconds=self.sleep_timeout(), ocr_input_region=self.ocr_input_region.get(),
                          show_logic_diagrams=self.show_logic_diagrams.get(),
                          detector_model=model_setting(self.detector_model_path))
            for obsolete in OBSOLETE_SETTINGS:
                values.pop(obsolete, None)
            write_settings_section('ui', values)
            return True
        except Exception as exc:
            logging.exception('Settings not saved')
            messagebox.showerror('Settings not saved', str(exc), parent=self.root)
            return False

    def toggle_logging(self):
        text = ('Logging on: clicked readings are saved' if self.logging_enabled.get()
                else 'Logging off: clicked readings are not saved')
        self.archive_state.set(text)
        self.ocr_state.set(text)

    def preprocessing_description(self):
        cfg = self.snapshot_preprocessing
        if cfg is None:
            return 'Standard preprocessing / Original first'
        return cfg['mode'].capitalize()+' / '+cfg['stage']+': '+' → '.join(cfg['presets'])

    def configure_preprocessing(self):
        from preprocessing_ui import edit

        def apply(config):
            try:
                write_settings_section('preprocessing', config)
            except OSError as exc:
                logging.exception('Snapshot preprocessing not saved')
                messagebox.showerror('Snapshot preprocessing not saved',
                                     str(exc) + '\n\nThe previous settings remain active.', parent=self.root)
                return
            self.snapshot_preprocessing = config
            self.preprocessing_label.set(self.preprocessing_description())
            self.invalidate('Snapshot preprocessing changed — scan again')
            self.preview_snapshot()
        edit(self.root, self.snapshot_preprocessing, apply)

    def ensure_detector_worker(self):
        if self.detector_worker is None:
            self.detector_worker = DetectionWorker()
            self.detector_worker.configure_preprocessing(self.detector_alignment_mode)
        return self.detector_worker

    def use_detector_model(self, path):
        """Load a model from DATA/models. The path is stored resolved, exactly as the
        detector worker publishes it, so cached detections match (0.8.4.8)."""
        self.detector_model_path = str(Path(path).resolve())
        self.ensure_detector_worker().load(self.detector_model_path)
        self.model_filename.set(Path(self.detector_model_path).name)
        self.detections_state = None
        self.detector_submitted = -1

    def toggle_detector(self):
        """Experimental: draw the trained model's IC-body boxes on the video.
        Click inside a box to select that chip (box + margin) as the region."""
        if self.show_detections.get():
            self.ensure_detector_worker()
        self.detections_state = None
        self.detector_submitted = -1

    def choose_detector(self):
        path = filedialog.askopenfilename(title='Import or select chip-body model in DATA/models',
                                          initialdir=str(MODELS), parent=self.root,
                                          filetypes=[('ONNX model', '*.onnx'), ('All files', '*.*')])
        if not path:
            return
        from shared_data import install_model
        try:
            path = install_model(path, DATA)
        except Exception as exc:
            messagebox.showerror('Model import failed', str(exc), parent=self.root)
            return
        self.use_detector_model(path)
        self.invalidate('Detector model changed — scan again')
        self.show_detections.set(True)
        self.state.set('Detector model: '+Path(path).name+' (uses '+Path(path).with_suffix('.json').name+
                       ' if present)')

    def toggle_targeted_original(self):
        self.targeted_original_mode = bool(self.targeted_original.get())
        self.invalidate('Treatment fallback changed — scan again')

    def toggle_detector_alignment(self):
        self.detector_alignment_mode = bool(self.detector_alignment.get())
        if self.detector_worker is not None:
            self.detector_worker.configure_preprocessing(self.detector_alignment_mode)
        self.detections_state = None
        self.detector_submitted = -1
        self.invalidate('Detector alignment changed — scan again')

    def toggle_fast(self):
        # Plain bool: read by the OCR worker thread without touching Tk.
        self.fast_mode = bool(self.fast_scan.get())
        self.invalidate('Scan mode changed — scan again')

    def toggle_scan_verification(self):
        self.verification.reset(time.monotonic())
        self.save_settings()

    def toggle_observation_live(self):
        self.observation_mode = bool(self.observation_live.get())
        self.invalidate('Observation Live enabled' if self.observation_mode else 'Standard Live enabled')

    def toggle_live(self):
        self.wake_for_action()
        self.invalidate('Live: hold the board still…' if self.live.get() else 'Live recognition off')
        if self.live.get() and self.multi_mode:
            self.overlay = 'Live recognition is paused while Multi-chip scan is on — press Enter to scan'
        self.next_live_scan = 0.0

    def toggle_multi_chip(self):
        self.multi_mode = bool(self.multi_chip.get())
        if self.multi_mode:
            self.invalidate('Multi-chip scan on — select the area with the chips (or the whole view) '
                            'and press Enter' + ('; Live recognition paused' if self.live.get() else ''))
        else:
            self.invalidate('Multi-chip scan off — single-chip scanning' +
                            ('; Live recognition resumes' if self.live.get() else ''))

    def open_folder(self, folder, title='Folder', intro=''):
        try:
            Path(folder).mkdir(parents=True, exist_ok=True)
            os.startfile(str(folder))
        except Exception as exc:
            parent = self.settings_window if self.settings_window is not None else self.root
            messagebox.showinfo(title, intro+str(folder)+'\n\n'+str(exc), parent=parent)

    def open_data_folder(self):
        self.open_folder(DATA, 'Data folder', 'Captures, confirmed readings and logs are in:\n')

    def show_config_warnings(self):
        warnings = configuration_diagnostics()['warnings']
        if warnings:
            messagebox.showwarning('Configuration defaults active',
                '\n\n'.join(warnings) + '\n\nFix the files and restart ICOCR. Your files were not changed.',
                parent=self.root)
