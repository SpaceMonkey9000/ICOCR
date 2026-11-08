"""Display references from the shared DATA/components.sqlite database only."""
import logging
from icdb_references import ReferenceIndex
from project_paths import DATA


class DiagramLibrary:
    def __init__(self, data_folder=None, background=True):
        from pathlib import Path
        self.folder = Path(data_folder or DATA)
        from shared_data import database_file
        self.references = ReferenceIndex(database_file(self.folder))
        self.reason = 'No pinout linked in ICDB'
        if background:self.references.start()
        else:self.references.poll()

    def choices(self, row):
        if not row or row.get('provisional') or row.get('rejection_reason'):return []
        match = row.get('selected_database_match')
        if not match:return []
        choices, reason = self.references.choices(match)
        self.reason = reason or ('No pinout linked in ICDB' if not choices else '')
        if not choices and 'unavailable' in self.references.status:
            self.reason = self.references.status
        return choices

    def lookup(self, row):
        choices = self.choices(row)
        match = (row or {}).get('selected_database_match') or {}
        return default_reference(choices,match.get('package',''))

    def close(self):self.references.close()
    def refresh(self):self.references.refresh()
    @property
    def generation(self):return self.references.generation
    @property
    def status(self):return self.references.status


def default_reference(choices, package='', remembered=None):
    from icdb_references import package_key
    for entry in choices:
        if entry.get('reference_id') == remembered:return entry
    exact = [e for e in choices if package and package_key(e['package']) == package_key(package)]
    pool = exact or choices
    if not pool:return None
    defaults = [e for e in pool if e.get('is_default')]
    if defaults:return defaults[0]
    return pool[0]


def reference_labels(choices):
    labels = []
    for entry in choices:
        label = entry.get('package') or 'General reference'
        if entry.get('pin_count'):label += f" · {entry['pin_count']} pins"
        if entry.get('label'):label += ' — '+entry['label']
        if entry.get('is_default'):label += ' (default)'
        labels.append(label)
    duplicates = {label for label in labels if labels.count(label)>1}
    return [label+' — '+e['path'].name+' ['+e['reference_id']+']' if label in duplicates else label
            for label,e in zip(labels,choices)]


class DiagramPanel:
    def __init__(self, parent):
        import tkinter as tk
        from tkinter import ttk
        self.library = DiagramLibrary()
        self.frame = ttk.LabelFrame(parent, text='Pinout / reference', padding=5)
        self.title = tk.StringVar(value='Pinout unavailable')
        from status_panel import StatusPanel
        self.title_panel = StatusPanel(self.frame, self.title, lines=1)
        self.title_panel.frame.pack(fill='x')
        self.image_area = tk.Frame(self.frame, height=260, background='white')
        self.image_area.pack_propagate(False)
        self.image_label = tk.Label(self.image_area, cursor='hand2', background='white',
                                    borderwidth=0, highlightthickness=0, padx=0, pady=0)
        self.image_label.place(relx=0.5, rely=0.5, anchor='center')
        self.image_area.bind('<Configure>', self._render_image)
        self.image_label.bind('<Button-1>', self.enlarge)
        self.selection_frame = ttk.Frame(self.frame)
        self.selection_frame.pack(side='bottom',fill='x',pady=(2,0))
        ttk.Label(self.selection_frame,text='Package / reference:').pack(anchor='w')
        self.selector = ttk.Combobox(self.selection_frame,state='readonly',width=28)
        self.selector.pack(fill='x')
        self.selector.bind('<<ComboboxSelected>>',self.select_reference)
        self.choices = []
        self.remembered = {}
        self.note = tk.StringVar(value='Waiting for a reading')
        self.note_panel = StatusPanel(self.frame, self.note, lines=1)
        self.note_panel.frame.pack(side='bottom', fill='x')
        self.image_area.pack(fill='both', expand=True, pady=4)
        self.current = None
        self.image = None
        self.last_device = None
        self.last_row = None
        self.last_token = None
        self.seen_generation = -1
        self.index_status = tk.StringVar(value=self.library.status)
        self._timer = self.frame.after(300, self._poll_index)
        self.frame.bind('<Destroy>', self._destroy, add='+')

    def _destroy(self, event):
        if event.widget == self.frame:
            self.library.close()
            self.frame.after_cancel(self._timer)

    def _poll_index(self):
        self.index_status.set(self.library.status)
        generation = self.library.generation
        if generation != self.seen_generation:
            self.seen_generation = generation
            if self.last_row is not None:
                self.update(self.last_row)
        self._timer = self.frame.after(300, self._poll_index)

    def select_reference(self, event=None):
        index = self.selector.current()
        if not 0 <= index < len(self.choices) or not self.last_row:return
        from icdb_references import identity
        match = self.last_row['selected_database_match']
        entry = self.choices[index]
        self.remembered[identity(match)] = entry['reference_id']
        self.update(self.last_row)

    def visible(self, enabled):
        self.frame.master.rowconfigure(1, weight=1 if enabled else 0, minsize=130 if enabled else 0)
        if enabled:
            self.frame.grid(row=1, column=0, sticky='nsew', padx=0, pady=(0,0))
        else:
            self.frame.grid_remove()

    def update(self, row, multi=False):
        if multi:
            self.clear('Single-chip mode only')
            return
        match = (row or {}).get('selected_database_match')
        if not match or row.get('provisional'):
            if self.last_device:
                self.note.set('Previous reading')
            return  # retain reference through OCR dropouts, explicitly labelled
        if row.get('rejection_reason'):
            self.clear('Reading unconfirmed')
            return
        self.last_row = row
        device = match['part'].strip().upper()
        from icdb_references import identity
        self.choices = self.library.choices(row)
        entry = default_reference(self.choices, match.get('package',''),
                                  getattr(self,'remembered',{}).get(identity(match)))
        if hasattr(self,'selector'):
            self.selector.configure(values=reference_labels(self.choices),
                state='readonly' if len(self.choices)>1 else 'disabled')
            if entry:self.selector.current(self.choices.index(entry))
            else:self.selector.set('Select a reference' if self.choices else 'No references')
        if not entry:
            self.image_label.configure(image='')
            self.image = self.current = self.last_token = None
            self.last_device = device
            self.title.set(device + ' — Pinout / reference')
            self.note.set('Select a reference' if self.choices else 'No pinout available')
            return
        token = (device, str(entry['path']), entry['stamp'], entry.get('reference_id'), entry.get('package'), entry.get('source'), entry.get('label'))
        if token == self.last_token:
            if self.current is not None:
                self.note.set(self.reference_note(entry, match))
            return
        self.image_label.configure(image='')
        self.image = self.current = None
        self.last_device = device
        try:
            from reference_images import load_reference_image
            self.image = load_reference_image(entry['path'])
            self._render_image()
            self.current = entry
            self.title.set(device + ' • ' + (entry['package'] or 'General reference'))
            self.last_token = token
            self.note.set(self.reference_note(entry, match))
        except Exception as exc:
            logging.warning('Diagram %s: %s', device, exc)
            self.image = self.current = None
            self.last_token = token
            self.title.set(device + ' — Pinout unavailable')
            self.note.set('Image unavailable')

    @staticmethod
    def reference_note(entry, match):
        from icdb_references import package_key
        wanted = match.get('package', '')
        if wanted and entry.get('package') and package_key(wanted) != package_key(entry['package']):
            return 'Package mismatch'
        return ''

    def _render_image(self, event=None):
        if self.image is None:
            return
        from PIL import Image, ImageOps, ImageTk
        # Reserve the same eight-pixel white border on all four image edges.
        width = max(1, self.image_area.winfo_width() - 16)
        height = max(1, self.image_area.winfo_height() - 16)
        scale = min(width / self.image.width, height / self.image.height)
        thumbnail = self.image.resize((max(1, int(self.image.width * scale)),
                                       max(1, int(self.image.height * scale))), Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(ImageOps.expand(thumbnail, border=8, fill='white'))
        self.image_label.configure(image=self.photo)

    def clear(self, reason='Waiting for a reading'):
        self.current = self.image = None
        self.last_device = self.last_row = self.last_token = None
        self.choices = []
        if hasattr(self,'selector'):
            self.selector.configure(values=(),state='disabled');self.selector.set('No references')
        self.title.set('Pinout unavailable')
        self.note.set(reason)
        self.image_label.configure(image='')

    def enlarge(self, event=None):
        if self.image is None:
            return
        import tkinter as tk
        from tkinter import ttk
        from PIL import ImageTk
        win = tk.Toplevel(self.frame)
        win.title(self.current['device'] + ' — diagram reference')
        im = self.image.copy()
        im.thumbnail((win.winfo_screenwidth()-100, win.winfo_screenheight()-180))
        photo = ImageTk.PhotoImage(im)
        label = ttk.Label(win, image=photo)
        label.image = photo
        label.pack()
        ttk.Label(win, text=self.current['package']+' • Reference: '+self.current['source'], wraplength=850).pack(padx=10,pady=10)
