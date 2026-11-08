"""Camera/image input, region selection and keyboard shortcuts."""
import logging
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import cv2
import numpy as np

from capture import Capture

DEFAULT_ROI = (.3, .2, .7, .8)
MIN_SELECTION = .01          # fraction of the image; smaller drags are clicks
DETECTION_MARGIN = .08       # region margin around a clicked detector box


class CaptureMixin:
    capture_class = Capture      # replaceable for replaying recorded frames
    TYPING_WIDGETS = (ttk.Entry, tk.Entry, ttk.Combobox, ttk.Button, ttk.Checkbutton,
                      tk.Button, tk.Checkbutton, tk.Text, ttk.Spinbox, tk.Spinbox)

    @staticmethod
    def list_cameras(backend):
        from cv2_enumerate_cameras import enumerate_cameras
        return [(c.index, c.name) for c in enumerate_cameras(backend)]

    def capture_backend(self):
        return cv2.CAP_DSHOW if self.backend.get() == 'DirectShow' else cv2.CAP_MSMF

    def refresh_devices(self):
        """List cameras on a worker thread (0.8.3.2); the window stays responsive.

        If the listing fails, plain device indices are offered instead (0.8.4.3).
        """
        backend = self.capture_backend()
        self.device_request += 1
        request = self.device_request
        self.devices = []
        self.device['values'] = []
        self.device.set('Searching for cameras…')

        def work():
            try:
                self.device_results.put((request, backend, self.list_cameras(backend), None))
            except Exception as exc:
                logging.exception('Background device enumeration failed')
                self.device_results.put((request, backend, None, exc))
        threading.Thread(target=work, name='camera-list', daemon=True).start()

    def accept_devices(self):
        while True:
            try:
                request, backend, devices, error = self.device_results.get_nowait()
            except queue.Empty:
                return
            if request != self.device_request:
                continue  # superseded by a later Refresh or backend change
            if error is not None:
                # 0.8.4.3: no second enumeration on the Tk thread (a hanging driver
                # froze the window); offer plain device indices instead.
                devices = []
                self.state.set('Camera list unavailable ('+str(error)+') — showing device indices')
            self.apply_devices(devices)
            if self.startup_capture_pending:
                self.startup_capture_pending = False
                if devices and not self.closing.is_set():
                    self.start()
                elif error is None:
                    self.state.set('No camera detected — connect a camera and press Refresh, then Start')

    def apply_devices(self, devices):
        self.devices = list(devices) or [(i, f'Device index {i}') for i in range(6)]
        self.device['values'] = [f'{i}: {name}' for i, name in self.devices]
        pick = next((n for n, (_, name) in enumerate(self.devices) if 'USB Capture HDMI' in name), 0)
        self.device.current(pick)

    def stop(self):
        self.startup_capture_pending = False
        self.idle_sleep.reset()
        if self.capture:
            self.capture.stop_event.set()
        self.frame = None
        self.invalidate('Capture stopped')
        self.clear_canvas()

    def start(self):
        self.startup_capture_pending = False
        self.wake_for_action()
        if self.capture and self.capture.is_alive():
            if self.capture.stop_event.is_set():
                self.state.set('Waiting for capture driver to close; try Start again shortly.')
            else:
                self.state.set('Stop the current capture before restarting.')
            return
        if not self.devices or self.device.current() < 0:
            self.state.set('Still searching for cameras — try Start again shortly.')
            return
        self.invalidate('Waiting for video…')
        self.frame = None
        resolution, fps = self.mode.get().split(' @')
        w, h = map(int, resolution.split('x'))
        index = self.devices[self.device.current()][0]
        self.capture = self.capture_class(index, self.capture_backend(), w, h, int(fps), self.mjpg.get())
        self.last_seq = -1
        self.capture.start()

    def open_image(self, path=None):
        if path is None:
            path = filedialog.askopenfilename(filetypes=[('Images', '*.jpg *.jpeg *.png *.bmp')],
                                              parent=self.root)
        if not path:
            return
        try:
            image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError('Image could not be decoded.')
            self.stop()
            self.frame = image
            self.frame_id += 1
            self.state.set(f'Image: {Path(path).name} | {image.shape[1]} × {image.shape[0]}')
            self.invalidate('Image loaded — select IC and scan')
        except Exception as exc:
            messagebox.showerror('Open image', str(exc), parent=self.root)

    def point(self, event):
        """Normalised image position of a canvas event, or None before the first frame is drawn."""
        if not self.rect:
            return None
        x, y, w, h = self.rect
        return (min(1, max(0, (event.x-x)/w)), min(1, max(0, (event.y-y)/h)))

    def reset_selection(self, event=None):
        """Right-click restores the default region and cancels an active drag."""
        self.wake_for_action()
        self.drag = None
        self.drag_previous_roi = None
        self.roi = DEFAULT_ROI
        self.invalidate('Selection reset — press Enter or Scan')
        return 'break'

    def drag_start(self, event):
        self.wake_for_action()
        self.drag = self.point(event)
        if self.drag:
            self.drag_previous_roi = self.roi
            self.invalidate('Selecting region…')

    def drag_move(self, event):
        end = self.point(event)
        if self.drag and end:
            x, y = self.drag
            self.roi = (min(x, end[0]), min(y, end[1]), max(x, end[0]), max(y, end[1]))

    def drag_end(self, event):
        start = self.drag
        self.drag_move(event)
        self.drag = None
        if start is not None and (self.roi[2]-self.roi[0] < MIN_SELECTION or
                                  self.roi[3]-self.roi[1] < MIN_SELECTION):
            # A click: select the detector box under it, else keep the previous
            # selection (0.8.4.8; it used to reset to the default region).
            if not (self.frame is not None and self.select_detection(start)):
                self.roi = self.drag_previous_roi or self.roi
        self.invalidate('Region selected — press Enter or Scan')

    def select_detection(self, point):
        """Region from the model box under a click (normalised point), with margin."""
        h, w = self.frame.shape[:2]
        x, y = point[0]*w, point[1]*h
        shown = self._render_frame if self._render_frame is not None else self.frame
        hits = [d for d in self.visible_detections(shown)
                if d['box'][0] <= x <= d['box'][2] and d['box'][1] <= y <= d['box'][3]]
        if not hits:
            return False
        x1, y1, x2, y2 = min(hits, key=lambda d: (d['box'][2]-d['box'][0])*(d['box'][3]-d['box'][1]))['box']
        mx, my = DETECTION_MARGIN*(x2-x1), DETECTION_MARGIN*(y2-y1)
        self.roi = (max(0., (x1-mx)/w), max(0., (y1-my)/h), min(1., (x2+mx)/w), min(1., (y2+my)/h))
        return True

    def space(self, event):
        """Space: capture the current full frame, once per key press."""
        if isinstance(event.widget, self.TYPING_WIDGETS):
            return
        # Windows repeats KeyPress while held; X11 sends Release+Press pairs at
        # the same instant. Neither counts as a new press.
        repeat = self.space_down or (event.time and event.time - self.space_released_at < 40)
        self.space_down = True
        if not repeat:
            self.capture_image()
        return 'break'

    def space_released(self, event):
        self.space_down = False
        self.space_released_at = event.time or 0

    def space_focus_changed(self, event=None):
        """A release while a dialog had focus never reached the main window, so
        the next press was taken for a held key (0.8.8): forget the held state."""
        self.space_down = False

    def enter(self, event):
        """Enter: scan (Space did this before 0.8.3.5)."""
        if isinstance(event.widget, self.TYPING_WIDGETS):
            return
        self.scan()
        return 'break'

    def capture_image(self):
        self.wake_for_action()
        if self.frame is None:
            self.ocr_state.set('No current image to capture')
            return
        if self.documentation.capture(self.frame):
            self.ocr_state.set('Saving image…')
