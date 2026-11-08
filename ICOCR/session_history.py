"""In-memory recognised-marking history, independent of the live results panel."""
from copy import deepcopy
import logging
import time
import tkinter as tk
from tkinter import ttk, messagebox
import urllib.parse
import webbrowser
from component_catalog import describe
from click_log import record_click


class SessionHistory:
    def __init__(self, root, log_path):
        self.root = root
        self.log_path = log_path
        self.entries = []
        self.indices = {}
        self.window = None
        self.caption = tk.StringVar(master=root, value='Session history (0)')

    def add(self, rows, database_loaded):
        changed = False
        for row in rows:
            key = row.get('text',row['key']).strip().upper()
            if key in self.indices:
                # Upgrade earlier unmatched/partial observations when a better match arrives.
                entry = self.entries[self.indices[key]]
                def quality(r):
                    matches = r.get('trusted_database_matches',[])
                    return 2 if any(m.get('match_type')=='exact' for m in matches) else int(bool(matches))
                if quality(row) > quality(entry['row']):
                    entry.update(row=deepcopy(row),database_loaded=database_loaded)
                    changed = True
                continue
            self.indices[key] = len(self.entries)
            self.entries.append(dict(row=deepcopy(row),time=time.strftime('%H:%M:%S'),
                                     database_loaded=database_loaded))
            changed = True
        self.caption.set(f'Session history ({len(self.entries)})')
        if changed and self.window is not None and self.window.winfo_exists():
            self.refresh()

    def open(self):
        if self.window is not None and self.window.winfo_exists():
            self.window.lift(); return
        self.window = tk.Toplevel(self.root)
        self.window.title('Session history — recognised markings')
        self.window.geometry('820x600')
        ttk.Label(self.window,text='One entry per marking • select with arrow keys to review • click to search',padding=8).pack(fill='x')
        frame=ttk.Frame(self.window);frame.pack(fill='both',expand=True,padx=8)
        self.listbox=tk.Listbox(frame,exportselection=False,height=12)
        scroll=ttk.Scrollbar(frame,orient='vertical',command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');self.listbox.pack(fill='both',expand=True)
        self.details=tk.Text(self.window,height=10,wrap='word',state='disabled')
        self.details.pack(fill='both',expand=True,padx=8,pady=8)
        ttk.Button(self.window,text='Clear session history',command=self.clear).pack(anchor='e',padx=8,pady=(0,8))
        self.listbox.bind('<<ListboxSelect>>',self.select)
        self.listbox.bind('<ButtonRelease-1>',self.click)
        self.refresh()

    def refresh(self):
        selection=self.listbox.curselection()
        view=self.listbox.yview()
        self.listbox.delete(0,'end')
        for entry in self.entries:
            row=entry['row']
            label=row.get('function_summary') or 'No database match'
            self.listbox.insert('end',f"{entry['time']}   {row['text']} — {label}")
        if selection and selection[0]<len(self.entries):
            self.listbox.selection_set(selection[0]);self.select()
        if view:self.listbox.yview_moveto(view[0])

    def select(self,event=None):
        selected=self.listbox.curselection()
        if not selected:return
        entry=self.entries[selected[0]];row=entry['row']
        text=f"{row['text']} — first seen {entry['time']}\n\n"+describe(row.get('database_matches',[]))
        self.details.configure(state='normal');self.details.delete('1.0','end')
        self.details.insert('end',text);self.details.configure(state='disabled')

    def click(self,event):
        if not self.entries:return
        index=self.listbox.nearest(event.y);bounds=self.listbox.bbox(index)
        if bounds is None or not bounds[1]<=event.y<bounds[1]+bounds[3]:return
        self.listbox.selection_clear(0,'end');self.listbox.selection_set(index);self.select()
        entry=self.entries[index];row=entry['row']
        now=time.monotonic()
        previous=getattr(self,'last_click',('',0))
        if previous[0]==row['key'] and now-previous[1]<.5:return 'break'
        self.last_click=(row['key'],now)
        try:
            record_click(self.log_path,row,database_loaded=entry['database_loaded'])
        except Exception as exc:
            logging.exception('Could not log session history click')
            messagebox.showerror('Click was not logged',str(exc),parent=self.window)
        webbrowser.open('https://www.google.com/search?q='+urllib.parse.quote_plus(row['text']+' IC datasheet'))
        return 'break'

    def clear(self):
        self.entries.clear();self.indices.clear();self.caption.set('Session history (0)')
        self.refresh()
        self.details.configure(state='normal');self.details.delete('1.0','end');self.details.configure(state='disabled')
