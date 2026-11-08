"""User-sized sidebar panes; proportions persist independently of scan updates."""
import json
import logging
import tkinter as tk
from tkinter import ttk
from user_paths import CONFIG_DIR

DEFAULT = (0.25, 0.32, 0.43)


class SidebarLayout:
    def __init__(self, parent):
        self.path = CONFIG_DIR / 'sidebar_layout.json'
        self.ratios = DEFAULT
        try:
            values = json.loads(self.path.read_text('utf-8'))['proportions']
            if (isinstance(values, list) and len(values) == 3 and
                    all(type(x) in (int, float) and 0.05 <= x <= .9 for x in values) and
                    .99 <= sum(values) <= 1.01):
                self.ratios = tuple(values)
        except (OSError, ValueError, KeyError, TypeError):
            pass
        self.widget = tk.PanedWindow(parent, orient='vertical', sashwidth=7,
                                     sashrelief='raised', borderwidth=0, opaqueresize=True)
        self.widget.pack(fill='both', expand=True)
        self.frames = [ttk.Frame(self.widget, padding=(6, 2)) for _ in range(3)]
        self.minimums = (100, 210, 160)
        for frame, minimum in zip(self.frames, self.minimums):
            self.widget.add(frame, minsize=minimum, stretch='always')
        self.dragging = False
        self.pending = None
        self.widget.bind('<Configure>', self.resize)
        self.widget.bind('<ButtonPress-1>', self.press)
        self.widget.bind('<ButtonRelease-1>', self.release)
        self.widget.bind('<Destroy>', self.destroy, add='+')

    def press(self, event):
        self.dragging = bool(self.widget.identify(event.x, event.y))

    def resize(self, event=None):
        if self.dragging:
            return
        if self.pending:
            self.widget.after_cancel(self.pending)
        self.pending = self.widget.after_idle(self.apply)

    def apply(self):
        self.pending = None
        height = self.widget.winfo_height() - 14
        if height <= 1:
            return
        # Allocate minimum sizes first, then distribute remaining space.
        sizes = [max(m, r * height) for m, r in zip(self.minimums, self.ratios)]
        excess = sum(sizes) - height
        spare = sum(max(0, s-m) for s, m in zip(sizes, self.minimums))
        if excess > 0 and spare:
            sizes = [s - min(excess, spare)*max(0, s-m)/spare for s, m in zip(sizes, self.minimums)]
        self.widget.sash_place(0, 0, round(sizes[0]))
        self.widget.sash_place(1, 0, round(sizes[0]+sizes[1]+7))

    def release(self, event=None):
        if not self.dragging:
            return
        self.dragging = False
        self.widget.update_idletasks()
        heights = [f.winfo_height() for f in self.frames]
        total = sum(heights)
        if total:
            self.ratios = tuple(h/total for h in heights)
            self.save()

    def save(self):
        try:
            from app_settings import write_json_atomic
            self.path.parent.mkdir(parents=True, exist_ok=True)
            write_json_atomic(self.path, {'proportions': self.ratios})
        except OSError:
            logging.exception('Could not save sidebar layout')

    def reset(self):
        self.ratios = DEFAULT
        self.apply()
        self.save()

    def destroy(self, event):
        if event.widget == self.widget and self.pending:
            self.widget.after_cancel(self.pending)
            self.pending = None


class CompactStatus:
    """Four stable visible lines; full information remains scrollable."""
    def __init__(self, parent, variable):
        self.variable = variable
        self.frame = ttk.Frame(parent)
        self.text = tk.Text(self.frame, height=4, width=1, wrap='word', relief='flat',
                            font='TkDefaultFont', background=ttk.Style().lookup('TFrame', 'background') or '#f0f0f0')
        bar = ttk.Scrollbar(self.frame, command=self.text.yview)
        bar.pack(side='right', fill='y')
        self.text.pack(side='left', fill='both', expand=True)
        self.text.configure(yscrollcommand=bar.set)
        self.trace = variable.trace_add('write', self.render)
        self.frame.bind('<Destroy>', self.destroy, add='+')
        self.render()

    def render(self, *args):
        self.text.configure(state='normal')
        self.text.delete('1.0', 'end')
        self.text.insert('1.0', self.variable.get())
        self.text.configure(state='disabled')

    def destroy(self, event):
        if event.widget == self.frame:
            self.variable.trace_remove('write', self.trace)
