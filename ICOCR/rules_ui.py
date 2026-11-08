"""Settings → Rules: searchable checkboxes, validation errors, restart-only saves."""
import tkinter as tk
from tkinter import ttk, messagebox

from config_loader import RULES, _LEGACY_DATA, validate
from rule_modules import RuleSnapshot, rules_directory, save_enabled


class RulesPage(ttk.Frame):
    def __init__(self, parent, open_folder):
        super().__init__(parent)
        self.pack(fill='both', expand=True)
        self.snapshot = None
        self.variables = {}
        ttk.Label(self, text='Enable or disable recognition rules. Restart ICOCR after saving.',
                  wraplength=550).pack(anchor='w', pady=(0, 6))
        ttk.Label(self, text=str(rules_directory()), wraplength=550).pack(anchor='w')
        bar = ttk.Frame(self)
        bar.pack(fill='x', pady=8)
        ttk.Label(bar, text='Find').pack(side='left')
        self.search = tk.StringVar(self)
        ttk.Entry(bar, textvariable=self.search).pack(side='left', fill='x', expand=True, padx=6)
        ttk.Button(bar, text='Refresh', command=self.refresh).pack(side='left')
        area = ttk.Frame(self)
        area.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(area, highlightthickness=0)
        scrollbar = ttk.Scrollbar(area, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.body = ttk.Frame(self.canvas)
        self.body_id = self.canvas.create_window((0, 0), window=self.body, anchor='nw')
        self.body.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(self.body_id, width=e.width))
        self.canvas.bind('<MouseWheel>', self.wheel)
        self.canvas.bind('<Button-4>', lambda e: self.canvas.yview_scroll(-3, 'units'))
        self.canvas.bind('<Button-5>', lambda e: self.canvas.yview_scroll(3, 'units'))
        self.status = tk.StringVar(self)
        ttk.Label(self, textvariable=self.status, wraplength=550).pack(fill='x', pady=6)
        buttons = ttk.Frame(self)
        buttons.pack(fill='x')
        ttk.Button(buttons, text='Open rules folder', command=lambda: open_folder(rules_directory())).pack(side='left')
        ttk.Button(buttons, text='Save rules', command=self.save).pack(side='right')
        self.search.trace_add('write', lambda *args: self.render())
        self.refresh()

    def wheel(self, event):
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, 'units')
        return 'break'

    def refresh(self):
        self.snapshot = RuleSnapshot(rules_directory(), _LEGACY_DATA, validate)
        self.variables = {row['id']: tk.BooleanVar(self, row['enabled']) for row in self.snapshot.modules}
        self.render()
        changed = self.snapshot.sha256 != RULES.sha256
        self.status.set(('Saved rules differ from this running session — restart ICOCR. ' if changed else '') +
                        f'{len(self.snapshot.modules)} rules; {len(self.snapshot.errors)} invalid files.')

    def render(self):
        if self.snapshot is None:
            return
        for widget in self.body.winfo_children():
            widget.destroy()
        query = self.search.get().strip().casefold()
        category = None
        for row in sorted(self.snapshot.modules, key=lambda r: (r['category'], r['name'], r['id'])):
            if query and query not in (row['id']+' '+row['name']+' '+row['category']).casefold():
                continue
            if row['category'] != category:
                category = row['category']
                ttk.Label(self.body, text=category, font=('Segoe UI', 10, 'bold')).pack(anchor='w', pady=(10, 3))
            check = ttk.Checkbutton(self.body, text=row['name'], variable=self.variables[row['id']],
                                    command=lambda: self.status.set('Unsaved changes — click Save rules, then restart ICOCR.'))
            check.pack(anchor='w', fill='x')
            check.bind('<MouseWheel>', self.wheel)
        for error in self.snapshot.errors:
            ttk.Label(self.body, text='Skipped: '+error['file']+'\n'+error['error'],
                      foreground='#b03030', wraplength=510).pack(anchor='w', pady=5)
        self.canvas.yview_moveto(0)

    def save(self):
        try:
            count = save_enabled(self.snapshot.modules,
                                 {key: var.get() for key, var in self.variables.items()}, validate, _LEGACY_DATA)
        except (OSError, ValueError, KeyError) as exc:
            messagebox.showerror('Rules not saved', str(exc), parent=self)
            return
        self.refresh()
        self.status.set(f'Saved {count} change(s). Restart ICOCR to apply.' if count else self.status.get())
