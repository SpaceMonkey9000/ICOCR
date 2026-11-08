"""Tk widget construction: main window, sidebar, footer and the Settings window."""
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import ic_detector
from documentation import Documentation
from logic_diagrams import DiagramPanel
from project_paths import DATA
from status_panel import StatusPanel
from ui_regions import REGIONS, Tooltip

BOOLEAN_VARIABLES = ('sleep_enabled', 'live', 'mjpg', 'logging_enabled', 'show_detections', 'auto_body', 'detector_body',
                     'fast_scan', 'targeted_original', 'scan_verification', 'observation_live',
                     'multi_chip', 'detector_alignment', 'show_all', 'show_logic_diagrams')
STRING_VARIABLES = ('sleep_seconds', 'ocr_input_region', 'state', 'ocr_state', 'footer_state', 'detail', 'marking',
                    'snap_label', 'archive_state', 'database_state', 'model_filename',
                    'preprocessing_label', 'runtime_state')
CAPTURE_MODES = ['3840x2160 @30', '1920x1080 @30', '1920x1080 @60', '1280x720 @30']
BACKGROUND = '#101923'


class LayoutMixin:
    def build(self):
        self.create_variables()
        settings = self.build_settings_window()
        self.build_toolbar(settings['Camera'])
        self.build_body()
        self.build_footer()
        self.build_camera_settings(settings['Camera'])
        self.build_recognition_settings(settings['Recognition'])
        self.build_database_settings(settings['Database & Documentation'])
        self.build_tools_settings(settings['Tools'])
        from rules_ui import RulesPage
        self.rules_page = RulesPage(settings['Rules'], self.open_folder)
        from ui_tooltips import install_control_help
        install_control_help(self.settings_window)

    def create_variables(self):
        """Tk variables that start from the defaults set by _init_state."""
        for names, kind in ((BOOLEAN_VARIABLES, tk.BooleanVar), (STRING_VARIABLES, tk.StringVar)):
            for name in names:
                setattr(self, name, kind(master=self.root, value=getattr(self, name).get()))
        self.model_filename.set(Path(self.detector_model_path).name if self.detector_model_path
                                else 'Default: ' + ic_detector.default_model().name)
        self.preprocessing_label.set(self.preprocessing_description())
        self.runtime_state.set('OCR processor: loads on first scan (requested '
                               + self.requested_device() + ')')

    def build_settings_window(self):
        window = self.settings_window = tk.Toplevel(self.root)
        window.title('Settings')
        window.geometry('620x640')
        window.withdraw()
        window.protocol('WM_DELETE_WINDOW', self.hide_settings)
        notebook = ttk.Notebook(window)
        notebook.pack(fill='both', expand=True, padx=12, pady=12)
        tabs = {}
        for title in ('Camera', 'Recognition', 'Rules', 'Database & Documentation', 'Tools'):
            tabs[title] = ttk.Frame(notebook, padding=12)
            notebook.add(tabs[title], text=title)
        ttk.Button(window, text='Close', command=self.hide_settings).pack(anchor='e', padx=12, pady=(0, 12))
        return tabs

    def build_toolbar(self, camera_settings):
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill='x')
        ttk.Label(top, text='Capture device').pack(side='left')
        self.device = ttk.Combobox(top, width=34, state='readonly')
        self.device.pack(side='left', padx=5)
        ttk.Button(top, text='Refresh', command=self.refresh_devices).pack(side='left')
        ttk.Button(top, text='Start', command=self.start).pack(side='left')
        ttk.Button(top, text='Stop', command=self.stop).pack(side='left', padx=3)
        ttk.Button(top, text='Settings', command=self.open_settings).pack(side='right')
        bar = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        bar.pack(fill='x')
        ttk.Button(bar, text='Open image', command=self.open_image).pack(side='left')
        ttk.Button(bar, text='Scan [Enter]', command=self.scan).pack(side='left')
        ttk.Checkbutton(bar, text='Live recognition', variable=self.live,
                        command=self.toggle_live).pack(side='left', padx=12)
        ttk.Button(bar, text='Capture image [Space]', command=self.capture_image).pack(side='left', padx=5)
        ttk.Button(bar, text='Open image folder',
                   command=lambda: self.open_folder(DATA/'captures')).pack(side='left', padx=5)

    def build_body(self):
        body = ttk.Panedwindow(self.root, orient='horizontal')
        body.pack(fill='both', expand=True, padx=8)
        self.canvas = tk.Canvas(body, bg=BACKGROUND, highlightthickness=0)
        body.add(self.canvas, weight=4)
        self.canvas.bind('<ButtonPress-1>', self.drag_start)
        self.canvas.bind('<B1-Motion>', self.drag_move)
        self.canvas.bind('<ButtonRelease-1>', self.drag_end)
        self.canvas.bind('<Button-3>', self.reset_selection)
        sidebar = ttk.Frame(body, width=340)
        body.add(sidebar, weight=1)
        from sidebar_layout import SidebarLayout, CompactStatus
        self.sidebar_layout = SidebarLayout(sidebar)
        snapshot, readings, pinout = self.sidebar_layout.frames
        ttk.Label(snapshot, text='Snapshot').pack(anchor='w')
        self.snapshot_status = StatusPanel(snapshot, self.snap_label, lines=1)
        self.snapshot_status.frame.pack(side='bottom', fill='x')
        self.snap_canvas = tk.Canvas(snapshot, bg=BACKGROUND, highlightthickness=0, height=120)
        self.snap_canvas.pack(fill='both', expand=True)
        self.snap_canvas.bind('<Configure>', self.resize_snapshot)
        ttk.Label(readings, text='Recognised markings').pack(anchor='w')
        self.status_panel = CompactStatus(readings, self.detail)
        self.status_panel.frame.pack(side='bottom', fill='x', pady=(2, 0))
        ttk.Button(readings, textvariable=self.session_history.caption,
                   command=self.session_history.open).pack(side='bottom', fill='x', pady=2)
        marking_scroll = ttk.Scrollbar(readings, orient='horizontal')
        marking_scroll.pack(side='bottom', fill='x')
        list_frame = ttk.Frame(readings)
        list_frame.pack(fill='both', expand=True)
        self.lines = tk.Listbox(list_frame, height=3, width=36, exportselection=False)
        vertical = ttk.Scrollbar(list_frame, command=self.lines.yview)
        vertical.pack(side='right', fill='y')
        self.lines.pack(side='left', fill='both', expand=True)
        self.lines.configure(xscrollcommand=marking_scroll.set, yscrollcommand=vertical.set)
        marking_scroll.configure(command=self.lines.xview)
        self.lines.bind('<<ListboxSelect>>', self.select_line)
        self.lines.bind('<ButtonRelease-1>', self.click_marking)
        pinout.columnconfigure(0, weight=1)
        self.diagram_panel = DiagramPanel(pinout)
        self.diagram_panel.visible(True)

    def resize_snapshot(self, event=None):
        if self.snapshot is not None:
            self.preview_snapshot()
            if self.multi_state is not None:
                self.show_multi_outline()
            else:
                self.show_body_outline()

    def build_footer(self):
        footer = ttk.Frame(self.root, padding=(8, 4), height=32)
        footer.pack(fill='x')
        footer.pack_propagate(False)
        for width, variable in ((135, self.footer_state), (390, self.state)):
            cell = ttk.Frame(footer, width=width)
            cell.pack(side='left', fill='y')
            cell.pack_propagate(False)
            ttk.Label(cell, textvariable=variable, anchor='w').pack(fill='both', expand=True)
        cell = ttk.Frame(footer)
        cell.pack(side='left', fill='both', expand=True)
        cell.pack_propagate(False)
        ttk.Label(cell, textvariable=self.ocr_state, anchor='w').pack(fill='both', expand=True)

    def build_camera_settings(self, tab):
        sleep_row = ttk.Frame(tab)
        sleep_row.pack(fill='x', pady=(4, 12))
        ttk.Checkbutton(sleep_row, text='Sleep after inactivity', variable=self.sleep_enabled,
                        command=self.change_sleep_settings).pack(side='left')
        timeout = ttk.Spinbox(sleep_row, from_=5, to=3600, increment=5, width=6,
                              textvariable=self.sleep_seconds, command=self.change_sleep_settings)
        timeout.pack(side='left', padx=8)
        timeout.bind('<FocusOut>', lambda e: self.change_sleep_settings())
        Tooltip(timeout, 'Inactivity timeout in seconds: 5–3600. Default: 120. Saved custom values are retained.')
        ttk.Label(sleep_row, text='seconds').pack(side='left')
        ttk.Label(tab, text='Motion or a manual scan wakes recognition. Camera preview and the previous pinout stay visible.',
                  wraplength=550).pack(anchor='w')
        ttk.Label(tab, text='Camera changes apply when capture is restarted.').pack(anchor='w', pady=8)
        ttk.Label(tab, text='Capture backend').pack(anchor='w')
        self.backend = ttk.Combobox(tab, values=['DirectShow', 'MSMF'], width=11, state='readonly')
        self.backend.set('DirectShow')
        self.backend.pack(anchor='w', pady=5)
        self.backend.bind('<<ComboboxSelected>>', lambda e: self.refresh_devices())
        ttk.Label(tab, text='Requested resolution / FPS').pack(anchor='w')
        self.mode = ttk.Combobox(tab, values=CAPTURE_MODES, width=18, state='readonly')
        self.mode.set(CAPTURE_MODES[0])
        self.mode.pack(anchor='w', pady=5)
        ttk.Checkbutton(tab, text='Request MJPG', variable=self.mjpg).pack(anchor='w', pady=5)

    def build_recognition_settings(self, tab):
        model_row = ttk.Frame(tab)
        model_row.pack(fill='x', pady=5)
        ttk.Button(model_row, text='Import / select chip-body model…',
                   command=self.choose_detector).pack(side='left')
        ttk.Label(model_row, textvariable=self.model_filename, wraplength=250).pack(side='left', padx=8)
        live_detections = ttk.Checkbutton(tab, text='Show live chip detections', variable=self.show_detections,
                                          command=self.toggle_detector)
        live_detections.pack(anchor='w', pady=5)
        Tooltip(live_detections, 'Run the trained detector on the live image and display selectable chip '
                                 'outlines. OCR cropping is controlled separately by OCR input region.')
        ttk.Label(tab, text='OCR input region').pack(anchor='w')
        region = ttk.Combobox(tab, textvariable=self.ocr_input_region, values=REGIONS, state='readonly', width=46)
        region.pack(fill='x')
        region.bind('<<ComboboxSelected>>', self.change_input_region)
        ttk.Label(tab, text='Unsuccessful body scans can retry the full selection. Actual input and '
                            'fallback reasons appear below the snapshot.', wraplength=530).pack(anchor='w', pady=(2, 6))
        for text, variable, command in (
                ('Fast scan (0°/90° detection)', self.fast_scan, self.toggle_fast),
                ('Targeted treatment fallback', self.targeted_original, self.toggle_targeted_original),
                ('Scan verification', self.scan_verification, self.toggle_scan_verification),
                ('Observation Live (prototype)', self.observation_live, self.toggle_observation_live),
                ('Multi-chip scan (experimental): read every chip in the selection', self.multi_chip,
                 self.toggle_multi_chip)):
            ttk.Checkbutton(tab, text=text, variable=variable, command=command).pack(anchor='w')
        ttk.Button(tab, text='Snapshot preprocessing…', command=self.configure_preprocessing).pack(fill='x', pady=(5, 0))
        ttk.Label(tab, textvariable=self.preprocessing_label, wraplength=285).pack(anchor='w')
        for text, variable, command in (
                ('Detector alignment corrections', self.detector_alignment, self.toggle_detector_alignment),
                ('Show all recognised text', self.show_all, self.refresh_readings),
                ('Show pinout / reference', self.show_logic_diagrams,
                 lambda: self.diagram_panel.visible(self.show_logic_diagrams.get()))):
            ttk.Checkbutton(tab, text=text, variable=variable, command=command).pack(anchor='w')

    def build_database_settings(self, tab):
        # 0.8.3.8: Logging saves only readings the technician clicks (confirms).
        ttk.Checkbutton(tab, text='Log clicked readings', variable=self.logging_enabled,
                        command=self.toggle_logging).pack(anchor='w', pady=5)
        ttk.Label(tab, textvariable=self.archive_state, wraplength=285).pack(anchor='w')
        ttk.Button(tab, text='Choose DATA folder…', command=self.choose_data_folder).pack(fill='x', pady=(8, 2))
        ttk.Button(tab, text='Reload database', command=self.reload_database).pack(fill='x')
        ttk.Label(tab, text='DATA: '+str(DATA), wraplength=550).pack(fill='x', pady=5)
        ttk.Label(tab, textvariable=self.database_state, wraplength=285).pack(fill='x', pady=3)
        ttk.Button(tab, text='Open data folder', command=self.open_data_folder).pack(fill='x')
        ttk.Button(tab, text='Refresh pinout references',
                   command=lambda: self.diagram_panel.library.refresh()).pack(fill='x')
        ttk.Label(tab, textvariable=self.diagram_panel.index_status, wraplength=550).pack(fill='x')
        confirmed = DATA/Documentation.CONFIRMED_DIR
        ttk.Label(tab, text='Confirmed readings: '+str(confirmed), wraplength=550).pack(anchor='w', pady=8)
        ttk.Button(tab, text='Open confirmed folder',
                   command=lambda: self.open_folder(confirmed)).pack(anchor='w', pady=5)
        ttk.Label(tab, text='Clean captures (Space): '+str(DATA/'captures'), wraplength=550).pack(anchor='w', pady=8)

    def build_tools_settings(self, tab):
        from user_paths import CONFIG_DIR
        ttk.Button(tab, text='Open configuration folder',
                   command=lambda: self.open_folder(CONFIG_DIR)).pack(fill='x', pady=4)
        ttk.Button(tab, text='Reset layout', command=self.sidebar_layout.reset).pack(fill='x', pady=4)
        ttk.Button(tab, text='Diagnostics', command=self.show_diagnostics).pack(fill='x', pady=4)
        ttk.Label(tab, textvariable=self.runtime_state, wraplength=285, justify='left').pack(fill='x', pady=(0, 8))
