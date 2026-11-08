"""Snapshot-only policy editor. Worker configuration is captured per request."""
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from ic_preprocessing import INITIAL_PRESETS, configuration

ORDER = ('Original', 'Local contrast', 'Illumination')
_open_window = None   # 0.8.4.3: one editor at a time


def policy_from_file_data(data):
    """Preprocessing policy from a saved policy or an ICBENCH result file."""
    if not isinstance(data, dict):
        raise ValueError('Policy file must contain a JSON object')
    if 'options' in data:
        options = data['options']
        if not isinstance(options, dict):
            raise ValueError('"options" must be a JSON object')
        data = options.get('preprocessing')
    elif 'preprocessing' in data:
        data = data['preprocessing']
    return configuration(data)


def edit(parent, current, apply):
    global _open_window
    try:
        if _open_window is not None and _open_window.winfo_exists():
            _open_window.deiconify()
            _open_window.lift()
            _open_window.focus_set()
            return _open_window
    except tk.TclError:
        pass
    window = tk.Toplevel(parent);window.title('Snapshot preprocessing')
    _open_window = window
    frame = ttk.Frame(window, padding=14);frame.pack(fill='both', expand=True)
    cfg = current or configuration({'presets':['Original']})
    mode = tk.StringVar(value=cfg['mode'] if current else 'standard')
    stage = tk.StringVar(value=cfg['stage'])
    preset = tk.StringVar(value=cfg['presets'][0])
    sequence = tk.StringVar(value=', '.join(cfg['presets'] if len(cfg['presets'])>1 else ORDER))
    gamma = tk.StringVar(value=str(cfg['settings']['gamma']))
    sigma = tk.StringVar(value=str(cfg['settings']['background_sigma']))
    for row,(title,var,values) in enumerate([
        ('Policy',mode,('standard','single','fallback')),
        ('Stage',stage,('snapshot','crop')),
        ('Single preset',preset,INITIAL_PRESETS)]):
        ttk.Label(frame,text=title).grid(row=row,column=0,sticky='w',pady=5,padx=(0,10))
        ttk.Combobox(frame,textvariable=var,values=values,state='readonly',width=36).grid(row=row,column=1,sticky='ew')
    for row,(title,var) in enumerate([('Fallback order (comma separated)',sequence),('Gamma (<1 brightens)',gamma),('Background sigma (pixels)',sigma)],3):
        ttk.Label(frame,text=title).grid(row=row,column=0,sticky='w',pady=5,padx=(0,10))
        ttk.Entry(frame,textvariable=var,width=55).grid(row=row,column=1,sticky='ew')
    ttk.Label(frame,text='Applies to frozen snapshots only. Standard starts with Original and uses a targeted fallback when needed.\nFallback is experimental; it stops on an accepted result, which may still be wrong.').grid(row=6,column=0,columnspan=2,sticky='w',pady=8)
    def commit():
        try:
            result = None if mode.get() == 'standard' else configuration(dict(mode=mode.get(), stage=stage.get(),
                presets=[preset.get()] if mode.get()=='single' else [p.strip() for p in sequence.get().split(',')],
                settings=dict(gamma=float(gamma.get()),background_sigma=float(sigma.get()))))
            apply(result)
        except (ValueError,TypeError,OSError) as exc:
            messagebox.showerror('Preprocessing',str(exc),parent=window);return
        window.destroy()
    def load():
        path=filedialog.askopenfilename(parent=window,filetypes=[('JSON','*.json')])
        if not path:return
        try:
            value=policy_from_file_data(json.loads(Path(path).read_text('utf-8')))
            if value is None:mode.set('standard');return
            mode.set(value['mode']);stage.set(value['stage']);preset.set(value['presets'][0])
            sequence.set(', '.join(value['presets']));gamma.set(str(value['settings']['gamma']));sigma.set(str(value['settings']['background_sigma']))
        except (ValueError,TypeError,KeyError,AttributeError,OSError) as exc:messagebox.showerror('Cannot load policy',str(exc),parent=window)
    ttk.Button(frame,text='Load ICBENCH policy…',command=load).grid(row=7,column=0,sticky='w')
    ttk.Button(frame,text='Apply',command=commit).grid(row=7,column=1,sticky='e')
    return window
