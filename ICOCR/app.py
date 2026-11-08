"""ICOCR microscope OCR application: entry point and controller state.

0.8.4.8 split the former 2,750-line controller into mixins, one per concern:

=====================  ==========================================================
``app_layout``         Tk widget construction (main window and Settings)
``app_settings``       persisted preferences, Settings actions and option toggles
``app_database``       background loading/activation of the component catalogue
``app_capture``        camera/image input, region selection, keyboard shortcuts
``app_scanning``       scan requests, the OCR worker thread and its results
``app_live``           Live recognition: tracking, voting, verification, motion
``app_readings``       snapshot preview, Recognised markings list, confirmation log
``app_render``         video canvas and overlays
``app_diagnostics``    Diagnostics window
``app_lifecycle``      UI tick loop, background-result polling, dialogs, shutdown
``app_presenters``     Tk-free text for status, overlay labels and logged rows
``app_helpers``        Tk-free image/canvas helpers
``app_state``          data paths, logging set-up and click-log migration
=====================  ==========================================================

All controller state is created in :meth:`App._init_state` (tests call it on
``App.__new__(App)`` through ``tests/app_fixture.new_app``), so no method needs
``hasattr``/``getattr`` guards. Only the Tk thread touches widgets; the OCR worker
reads plain attributes (epoch, *_mode flags) and communicates through queues.
"""
import os

# Seed before configuration snapshots are imported when launched directly.
if __name__ == "__main__":
    from user_paths import prepare_config
    from project_paths import DATA as _startup_data
    prepare_config(_startup_data)

import collections
import queue
import threading
import tkinter as tk
from tkinter import ttk

from app_sleep import SleepMixin
from idle_sleep import IdleSleep
from user_paths import CONFIG_DIR, prepare_config
from app_capture import CaptureMixin, DEFAULT_ROI
from app_database import DatabaseMixin
from app_diagnostics import DiagnosticsMixin
from app_helpers import (ErrorLimiter, ItemPool, Value, display_text, preview_preprocessed,
                         preview_resize, roi_view, set_if_changed, snapshot_preview_size)
from app_layout import LayoutMixin
from app_lifecycle import LifecycleMixin
from app_live import LiveMixin
from app_readings import ReadingsMixin
from app_render import RenderMixin
from app_scanning import ScanningMixin
from app_settings import SettingsMixin, load_json, read_settings_section
from app_state import (CLICK_LOG, SESSION, configure_logging, legacy_click_logs,
                       migrate_click_log, prepare_data_folder)
from documentation import Documentation
from live_observation import ObservationPolicy
from overlay_worker import OverlayWorker
from performance import Performance
from project_paths import DATA, ROOT
from rescan_policy import RescanPolicy
from scan_verification import ScanVerification
from scene_guard import SceneGuard
from session_history import SessionHistory
from tracking_worker import TrackingWorker
from ui_regions import REGIONS
from version import VERSION

# Names kept importable from app for tools and tests written against 0.8.4.7.
__all__ = ['App', 'main', 'DATA', 'ROOT', 'CLICK_LOG', 'SESSION', 'SEED', 'migrate_click_log',
           'legacy_click_logs', 'ErrorLimiter', 'ItemPool', 'display_text', 'preview_preprocessed',
           'preview_resize', 'roi_view', 'set_if_changed', 'snapshot_preview_size']

# Bundled "known marking": known markings rank higher in OCR candidate selection.
# User entries from DATA/matches.json (saved by releases before 0.8.4.8) are merged in.
SEED = {'ULN2003': {'part': 'ULN2003 family', 'description': 'ST: seven-channel Darlington driver array',
                    'url': 'https://www.st.com/resource/en/datasheet/uln2003.pdf',
                    'source': 'Bundled example; confirm manufacturer/package'}}


def environment_flag(name, default='1'):
    return os.environ.get(name, default) != '0'


class App(SleepMixin, LayoutMixin, SettingsMixin, DatabaseMixin, CaptureMixin, ScanningMixin, LiveMixin,
          ReadingsMixin, RenderMixin, DiagnosticsMixin, LifecycleMixin):

    def __init__(self, root):
        prepare_data_folder()
        self._init_state()
        self.root = root
        root.title(f'ICOCR {VERSION}')
        if os.name == 'nt':
            root.iconbitmap(str(ROOT/'ICOCR.ico'))
        root.geometry('1400x950')
        root.minsize(950, 650)
        self.ui_preferences = read_settings_section('ui') or {}
        self.cache.update(load_json(DATA/'matches.json', dict, 'saved matches') or {})
        self.snapshot_preprocessing = self.load_preprocessing()
        self.documentation = Documentation(DATA)
        self.tracking_worker = TrackingWorker()
        self.overlay_worker = OverlayWorker()
        migrate_click_log()
        self.session_history = SessionHistory(root, CLICK_LOG)
        self.build()
        self.restore_settings()
        root.after(150, self.show_config_warnings)
        self.load_database_startup()
        self.ocr_thread = threading.Thread(target=self.ocr_worker, name='ocr', daemon=True)
        self.ocr_thread.start()
        self.startup_capture_pending = True
        self.refresh_devices()
        root.protocol('WM_DELETE_WINDOW', self.close)
        # 0.8.3.5: Space captures the full frame (one image per press), Enter scans.
        root.bind('<KeyPress-space>', self.space)
        root.bind('<KeyRelease-space>', self.space_released)
        root.bind('<FocusIn>', self.space_focus_changed, add='+')
        root.bind('<FocusOut>', self.space_focus_changed, add='+')
        root.bind('<Return>', self.enter)
        root.bind('<KP_Enter>', self.enter)
        root.bind('<F11>', lambda e: root.attributes('-fullscreen', not root.attributes('-fullscreen')))
        root.bind('<Escape>', lambda e: root.attributes('-fullscreen', False))
        root.after(40, self.tick)

    def _init_state(self):
        """Every controller attribute with its default; no Tk calls, no threads.

        Settings and status fields start as :class:`Value` objects; ``build``
        turns them into Tk variables with the same initial values. Workers and
        widgets that need Tk or start threads are None here and are created by
        ``__init__``/``build``.
        """
        # Tk objects (created by __init__ / build)
        self.root = None
        self.settings_window = None
        self.canvas = self.snap_canvas = self.lines = None
        self.device = self.backend = self.mode = None
        self.status_panel = self.diagram_panel = self.session_history = None
        # Background workers (threads; created by __init__ or on demand)
        self.documentation = None
        self.tracking_worker = self.overlay_worker = None
        self.detector_worker = None
        self.capture = None
        self.ocr_thread = None
        # Settings (Tk variables after build)
        targeted = environment_flag('ICOCR_TARGETED_ORIGINAL')
        alignment = environment_flag('ICOCR_DETECTOR_ALIGNMENT')
        for name, value in dict(
                sleep_enabled=True, sleep_seconds="120", live=False, mjpg=False, logging_enabled=True, show_detections=False,
                auto_body=True, detector_body=False, ocr_input_region=REGIONS[1],
                fast_scan=True, targeted_original=targeted, scan_verification=True,
                observation_live=False, multi_chip=False, detector_alignment=alignment,
                show_all=False, show_logic_diagrams=True).items():
            setattr(self, name, Value(value))
        # Plain copies of settings for the OCR thread (never reads Tk variables)
        self.fast_mode = True
        self.targeted_original_mode = targeted
        self.detector_alignment_mode = alignment
        self.observation_mode = False
        self.multi_mode = False
        # Status text (Tk variables after build)
        for name, value in dict(
                state='', ocr_state='', footer_state='— | — s', detail='No identification',
                marking='', snap_label='No snapshot yet', archive_state='',
                database_state='No component database loaded', model_filename='',
                preprocessing_label='', runtime_state='').items():
            setattr(self, name, Value(value))
        self.overlay = 'Start capture or open an image'
        # Preferences and saved data
        self.ui_preferences = {}
        self.cache = dict(SEED)
        self.snapshot_preprocessing = None
        self.detector_model_path = None
        self.click_log_path = CLICK_LOG
        # Frames, selection and scan bookkeeping
        self.frame = None
        self.frame_id = 0
        self.last_seq = -1
        self.roi = DEFAULT_ROI
        self.drag = None
        self.drag_previous_roi = None
        self.rect = None
        self.epoch = 0
        self.busy = False
        self.tasks = queue.Queue(maxsize=1)
        self.results = queue.Queue()
        self.scan_serial = 0
        self.active_scan_id = None
        self.request_live = False
        self.next_live_scan = 0.0
        self.closing = threading.Event()
        self.ocr_ready = threading.Event()
        self.shutdown_done = threading.Event()
        self.close_started = None
        self.shutdown_stragglers = []
        # Snapshot and readings
        self.snapshot = None          # image of the displayed readings (sidebar preview)
        self.snapshot_time = ''
        self.displayed_scan = None    # dict(scan_id, mode) of the displayed readings
        self.pending_snapshot = None  # Live scan in flight; shown once its result is accepted
        self.snap_preview_size = None
        self.snap_photo = None
        self.rows = []
        self.row_kinds = []
        self.filtered_rows = []
        self.diagnostics = {}
        self.scan_result = None
        self.manual_choice = None
        self.recognition_evidence = ''
        self.confirmed = set()        # (scan, chip, key, edited) saved or being saved
        self.confirm_pending = collections.deque()   # keys queued for the writer, in order
        self.last_list_click = ('', 0.)
        # Multi-chip
        self.multi_state = None
        self.multi_listed = []
        self.multi_choice_chip = None
        self.chips_lost = False
        # Live recognition
        self.idle_sleep = IdleSleep()
        self.scene_guard = SceneGuard()
        self.rescan_policy = RescanPolicy()
        self.verification = ScanVerification()
        self.verification_request = None
        self.observation_policy = ObservationPolicy()
        self.tracking_state = None
        self.tracking_pending = None
        self.last_tracking_version = -1
        self.submitted_frame_id = -1
        self.tracking_in_roi = False
        self.vote = None
        self.vote_serial = 0
        # Chip detector
        self.detections_state = None
        self.detector_submitted = -1
        # Database and camera list (filled by background threads)
        self.catalog = None
        self.database_path = None
        self.database_request = 0
        self.database_results = queue.Queue()
        self.startup_capture_pending = False
        self.devices = []
        self.device_request = 0
        self.device_results = queue.Queue()
        # Keyboard
        self.space_down = False
        self.space_released_at = -10**9
        # Rendering
        self.performance = Performance()
        self._preview_rate = None
        self._last_motion_result = None
        self.tick_errors = ErrorLimiter()
        self.pending_dialogs = []
        self.reset_canvas_state()

    def invalidate(self, text='Scene changed — scan again', preserve_reference=False):
        """Start a new epoch: results, tracking and choices of the old scene are dropped."""
        self.epoch += 1
        self.verification.reset()
        self.verification_request = None
        self.scene_guard.reset()
        self.tracking_worker.reset(self.epoch)
        self.overlay_worker.reset(self.epoch)
        self.tracking_state = None
        self.tracking_pending = None
        self.submitted_frame_id = -1
        self.rescan_policy.reset()
        self.observation_policy.reset()
        self.tracking_in_roi = False
        self.overlay = text
        self.vote = None
        self.manual_choice = None   # a new scene/region/setting needs a new choice
        self.multi_state = None     # multi-chip results belong to the old scene
        if self.diagram_panel is not None and not preserve_reference:
            self.diagram_panel.clear()


def main():
    prepare_config(DATA)
    prepare_data_folder()
    configure_logging()
    from data_lock import DataLease
    lease = DataLease(DATA)
    root = tk.Tk()
    ttk.Style().theme_use('clam')
    App(root)
    try:
        root.mainloop()
    finally:
        lease.close()


if __name__ == '__main__':
    main()
