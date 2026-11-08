"""Snapshot preview, the Recognised markings list and confirmed-reading logging."""
import logging
import time
import tkinter as tk
import urllib.parse
import webbrowser
from pathlib import Path
from tkinter import messagebox, simpledialog

import cv2
from PIL import Image, ImageTk

import multi_chip
import readings_list
from app_helpers import display_text, preview_preprocessed
from app_presenters import candidate_evidence, candidate_overlay, confirmation_fields
from app_state import SESSION
from click_log import record_click
from component_catalog import annotate
from ocr_core import normalize
from scan_result import build_scan_result
from status_panel import candidate_status

OUTLINE_COLOUR = '#57cfff'
DOUBLE_CLICK_SECONDS = .5


def outline_points(box, size, preview, offset=(0, 0)):
    """Image polygon -> flat snapshot-preview canvas coordinates."""
    (h, w), (pw, ph), (ox, oy) = size, preview, offset
    return [v for px, py in box for v in ((px-ox)*pw/w, (py-oy)*ph/h)]


class ReadingsMixin:
    # ------------------------------------------------------------ snapshot preview
    def preview_snapshot(self):
        if self.snapshot is None:
            return
        cfg = self.snapshot_preprocessing
        if cfg is None:
            preset = self.SNAPSHOT_MODE
        else:
            preset = cfg['presets'][0] if cfg['stage'] == 'snapshot' else 'Original'
        # 0.8.4.3: one INTER_AREA downscale, then preprocess the small image.
        box = (max(1, self.snap_canvas.winfo_width()), max(1, self.snap_canvas.winfo_height()))
        im = preview_preprocessed(self.snapshot, preset, cfg['settings'] if cfg else None, box=box)
        image = Image.fromarray(cv2.cvtColor(im, cv2.COLOR_BGR2RGB))
        self.snap_preview_size = image.size
        self.snap_photo = ImageTk.PhotoImage(image)
        self.snap_canvas.delete('all')
        self.snap_canvas.create_image(0, 0, image=self.snap_photo, anchor='nw')
        self.snap_label.set(f'Frozen {self.snapshot_time} • {preset}')

    def show_multi_outline(self):
        """Chip markings on the frozen selection preview (selection coordinates)."""
        state = self.multi_state
        if state is None or self.snap_preview_size is None or self.snapshot is None:
            return
        self.snap_canvas.delete('body_outline')
        size = self.snapshot.shape[:2]
        for chip in state['chips']:
            row = multi_chip.reading_of(chip)
            if row is None or row.get('box') is None:
                continue
            points = outline_points(row['box'], size, self.snap_preview_size, state['offset'])
            _, colour = multi_chip.describe(chip, self.catalog is not None)
            self.snap_canvas.create_polygon(*points, fill='', outline=colour, width=2, tags='body_outline')
            self.snap_canvas.create_text(points[0], points[1]-2, anchor='sw', fill=colour,
                                         text=str(chip['number']), font=('Segoe UI', 9, 'bold'),
                                         tags='body_outline')
        self.snap_label.set(f"Snapshot • multi-chip: {len(state['chips'])} chip(s)")

    def show_body_outline(self):
        # This canvas displays the immutable OCR snapshot, never a later frame.
        if self.snap_preview_size is None or self.snapshot is None:
            return
        self.snap_canvas.delete('body_outline')
        detection = self.diagnostics.get('body_detection', {})
        if detection.get('box') is not None:
            points = outline_points(detection['box'], self.snapshot.shape[:2], self.snap_preview_size)
            self.snap_canvas.create_polygon(*points, fill='', outline=OUTLINE_COLOUR, width=2, tags='body_outline')
        status = detection.get('status')
        if status:
            if status == 'applied':
                actual = 'model body' if detection.get('source') == 'model' else 'geometric body'
            else:
                actual = 'full selection'
            reason = (' — fallback: ' + detection.get('reason', 'body not found')
                      if status not in ('applied', 'disabled') else '')
            if detection.get('model_fallback_reason'):
                reason = ' — fallback: ' + detection['model_fallback_reason'] + reason
            recovery = self.diagnostics.get('body_recovery', {})
            if recovery.get('attempted') and not recovery.get('recovered'):
                reason += ' — full-selection retry also found no accepted match'
            self.snap_label.set('Scan input: ' + actual + reason)

    # -------------------------------------------------------------- readings list
    def fill_list(self, entries):
        """Replace the listbox with (label, colour) entries."""
        self.lines.delete(0, 'end')
        self.marking.set('')
        self.recognition_evidence = ''
        for index, (label, colour) in enumerate(entries):
            self.lines.insert('end', label)
            try:
                self.lines.itemconfig(index, foreground=colour)
            except (tk.TclError, AttributeError):
                pass

    def refresh_readings(self):
        """Every usable reading stays listed (0.8.3.4); the auto pick is marked ★,
        the technician's choice ✓. Clicking a reading makes it the choice."""
        if self.multi_state is not None:
            self.refresh_multi_readings()
            return
        if self.scan_result is None:
            self.scan_result = build_scan_result(self.filtered_rows,
                self.diagnostics.get('all_candidates', self.filtered_rows), self.catalog)
        chosen = self.manual_choice
        entries = readings_list.build(self.scan_result, self.diagnostics,
                                      show_all=self.show_all.get(), chosen=chosen)
        self.rows = [row for row, _ in entries]
        self.row_kinds = [kind for _, kind in entries]
        self.fill_list([(readings_list.label(row, kind), readings_list.COLOURS.get(kind, '#1b1b1b'))
                        for row, kind in entries])
        automatic = self.scan_result.get('selected') if self.scan_result else None
        if chosen is not None:
            overlay = readings_list.choice_status(chosen) + ': ' + chosen.get('text', chosen['key'])
        elif not entries:
            self.overlay = 'No text recognised — adjust the selection, focus or lighting and scan again'
            self.detail.set('Scan complete — no readable text.')
            return
        elif automatic:
            overlay = 'Readings ready'
        else:
            overlay = 'No automatic pick — choose the correct reading from the list'
        if chosen is not None or automatic:
            self.show_candidate(chosen if chosen is not None else automatic)
        else:
            self.detail.set('Scan complete — no automatic match.')
        self.overlay = overlay

    def refresh_multi_readings(self):
        """Multi-chip list: one line per chip that has a reading, numbered as on the video."""
        chips = self.multi_state['chips']
        listed = [chip for chip in chips if multi_chip.reading_of(chip) is not None]
        self.multi_listed = listed
        self.rows = [multi_chip.reading_of(chip) for chip in listed]
        self.row_kinds = ['multi'] * len(listed)
        colours = readings_list.COLOURS

        def colour(chip, row):
            if row.get('technician_choice'):
                return colours[readings_list.CHOSEN]
            return colours[readings_list.AUTO] if row is chip.get('selected') else colours[readings_list.OTHER]
        self.fill_list([(multi_chip.list_label(chip), colour(chip, row)) for chip, row in zip(listed, self.rows)])
        if not chips:
            self.overlay = 'Multi-chip: no chip marking found — enlarge the selection or move closer, then scan again'
            self.detail.set('Scan complete — no chip marking found.')
            return
        self.overlay = (f'Multi-chip: {len(chips)} chip(s) — click a reading in the list to search it'
                        if listed else 'Multi-chip: chips found, but no readable marking')
        self.detail.set(f'Scan complete — {len(chips)} chips; {len(listed)} readings.')

    def selected_index(self):
        selected = self.lines.curselection()
        return selected[0] if selected and selected[0] < len(self.rows) else None

    def show_candidate(self, row):
        self.overlay = candidate_overlay(row)
        self.recognition_evidence = candidate_evidence(row, self.cache.get(row['key']))
        self.detail.set(candidate_status(row))

    def select_line(self, event=None):
        index = self.selected_index()
        if index is not None:
            row = self.rows[index]
            self.marking.set(display_text(row))
            self.show_candidate(row)

    # ------------------------------------------------------- technician choices
    def click_marking(self, event):
        # Do not search on programmatic selection changes or clicks below the rows.
        if not self.rows:
            return
        index = self.lines.nearest(event.y)
        bounds = self.lines.bbox(index)
        if bounds is None or not (bounds[1] <= event.y < bounds[1]+bounds[3]):
            return
        if not 0 <= index < len(self.rows):
            return
        if tuple(self.lines.curselection()) != (index,):
            # <<ListboxSelect>> already ran select_line for the row under the press.
            self.lines.selection_clear(0, 'end')
            self.lines.selection_set(index)
            self.select_line()
        now = time.monotonic()
        row = self.rows[index]
        last_key, last_time = self.last_list_click
        # A double-click is one search and one log row (as in session history).
        if row['key'] == last_key and now-last_time < DOUBLE_CLICK_SECONDS:
            return 'break'
        self.last_list_click = (row['key'], now)
        self.log_click(row)
        self.choose_reading(row)
        self.confirm_reading(row)
        self.search()
        return 'break'

    def log_click(self, row):
        try:
            record_click(self.click_log_path, row, database_loaded=self.catalog is not None)
        except Exception as exc:
            logging.exception('Could not save recognised-marking click')
            messagebox.showerror('Click was not logged', 'Could not write the click history. '+str(exc),
                                 parent=self.root)

    def edit_reading(self):
        """Correct a near-miss reading (e.g. AISAM9G45 -> ATSAM9G45) and use it
        as the technician choice: database lookup, search and log as for a click."""
        index = self.selected_index()
        base = self.rows[index] if index is not None else (
            self.manual_choice or (self.scan_result or {}).get('selected'))
        initial = self.marking.get().strip() or (base or {}).get('text', '')
        text = simpledialog.askstring('Edit reading', 'Correct the marking text as printed on the IC:',
                                      initialvalue=initial, parent=self.root)
        if not text or not normalize(text):
            return
        text = ' '.join(text.strip().upper().split())
        row = dict(key=normalize(text), text=text, raw_text=text, score=1., support=1, rotation=0,
                   box=(base or {}).get('box'), kind='edited', rank=0., conflicts=[],
                   status='Clarified', edited_from=(base or {}).get('key', ''),
                   evidence='Typed by the technician' + (' from OCR reading ' + base['key'] if base else ''))
        try:
            row = annotate([row], self.catalog)[0]
        except Exception:
            logging.exception('Database lookup of an edited reading failed')
        row.update(status='Clarified', kind='edited')
        self.log_click(row)
        self.choose_reading(row)
        self.confirm_reading(row, edited=True)
        self.search()

    def choose_reading(self, row):
        """Technician override: the clicked reading replaces the automatic pick
        for this scene (status, session history and, with Logging on, the scan log)."""
        if self.multi_state is not None:
            self.choose_multi_reading(row)
            return
        self.manual_choice = dict(row, technician_choice=True)
        if self.diagram_panel is not None:
            self.diagram_panel.update(dict(row, rejection_reason='', provisional=False))
        if self.session_history is not None:
            self.session_history.add([self.manual_choice], database_loaded=self.catalog is not None)
        self.refresh_readings()
        self.lines.selection_clear(0, 'end')
        self.lines.selection_set(0)
        self.marking.set(display_text(row))
        self.show_candidate(self.rows[0])
        self.overlay = readings_list.choice_status(self.manual_choice) + ': ' + self.manual_choice.get('text', self.manual_choice['key'])

    def choose_multi_reading(self, row):
        """Multi-chip: the choice belongs to the chip selected in the list."""
        selected = self.lines.curselection()
        listed = self.multi_listed
        chip = listed[selected[0]] if selected and selected[0] < len(listed) else None
        choice = dict(row, technician_choice=True)
        choice.pop('multi_unconfirmed', None)   # the technician confirmed it
        self.multi_choice_chip = chip
        if chip is not None:
            if choice.get('box') is None:
                choice['box'] = (multi_chip.reading_of(chip) or {}).get('box')
            chip['choice'] = choice
        if self.session_history is not None:
            self.session_history.add([choice], database_loaded=self.catalog is not None)
        self.refresh_readings()
        index = next((i for i, c in enumerate(self.multi_listed) if c is chip), None)
        self.lines.selection_clear(0, 'end')
        if index is not None:
            self.lines.selection_set(index)
        self.marking.set(display_text(choice))
        self.show_candidate(choice)
        self.overlay = (f"Chip {chip['number']}: " if chip is not None else '') + \
            readings_list.choice_status(choice) + ': ' + choice.get('text', choice['key'])
        self.show_multi_outline()

    def confirm_reading(self, row, edited=False):
        """0.8.3.8 logging: a clicked (or edited) reading is a technician
        confirmation. Save the snapshot as JPEG plus one row in confirmed.csv."""
        if not self.logging_enabled.get() or row is None:
            return False
        multi = self.multi_state
        chip = self.multi_choice_chip if multi is not None else None
        # 0.8.8: log the scan the list shows (its snapshot, id and mode), never a
        # later Live or verification scan that did not replace it.
        shown = self.displayed_scan or dict(scan_id=self.active_scan_id,
                                            mode='live' if self.request_live else 'scan')
        scan_id = shown['scan_id']
        if chip is not None:
            x0, y0, x1, y1 = chip['region']
            snapshot = multi['frame'][y0:y1, x0:x1]
            automatic = chip.get('selected')
            lines = (chip.get('scan_result') or {}).get('all_candidates', [])
            mode, number = 'multi-chip', chip.get('number', '')
            scan_id = multi.get('scan_id', scan_id)
        else:
            snapshot = self.snapshot
            automatic = (self.scan_result or {}).get('selected')
            lines = (self.scan_result or {}).get('all_candidates', [])
            mode, number = shown['mode'], ''
        if snapshot is None or not snapshot.size:
            self.ocr_state.set('Not logged: no snapshot belongs to this reading')
            return False
        key = (scan_id, number, row.get('key'), bool(edited))
        if key in self.confirmed:
            self.ocr_state.set('Still saving this reading…' if key in self.confirm_pending
                               else 'Already logged for this scan')
            return False
        # Several clicks on one scan: the last row of a scan is the final answer.
        fields = confirmation_fields(row, automatic, lines, edited, mode, number,
                                     scan=f'{SESSION}-{scan_id}',
                                     database=Path(self.database_path).name if self.database_path else '')
        try:
            accepted = self.documentation.confirm(snapshot, fields)
        except Exception as exc:
            logging.exception('Confirmed reading not saved')
            self.ocr_state.set('Not logged: '+str(exc))
            return False
        if accepted:
            # Blocks a second row while saving; accept_documentation forgets the
            # key again if the write fails, so clicking the reading retries it.
            self.confirmed.add(key)
            self.confirm_pending.append(key)
            self.ocr_state.set('Logging '+fields['confirmed_text']+
                               (' (corrected)' if fields['corrected'] == 'yes' else '')+'…')
        return accepted

    def search(self):
        text = self.marking.get().strip()
        if text:
            webbrowser.open('https://www.google.com/search?q='+urllib.parse.quote_plus(text+' IC datasheet'))
