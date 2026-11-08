"""Pure migration helpers keep old cropping combinations exactly equivalent."""
REGIONS = ('Full selection', 'Automatic body crop — geometric', 'Automatic body crop — trained model')


def region_from_preferences(preferences):
    value = preferences.get('ocr_input_region')
    if value in REGIONS:
        return value
    if preferences.get('auto_body', True) is False:
        return REGIONS[0]
    return REGIONS[2] if preferences.get('detector_body', False) is True else REGIONS[1]


class Tooltip:
    def __init__(self, widget, text):
        self.window = None
        self.widget, self.text = widget, text
        self.enabled = widget.winfo_toplevel() is not widget._root()
        if not self.enabled:
            return
        widget.bind('<Enter>', self.show, add='+')
        widget.bind('<Leave>', self.hide, add='+')
        widget.bind('<ButtonPress>', self.hide, add='+')
        widget.bind('<Destroy>', self.hide, add='+')

    def show(self, event=None):
        import tkinter as tk
        from tkinter import ttk
        if not self.enabled or self.window:
            return
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.wm_geometry(f'+{self.widget.winfo_rootx()+10}+{self.widget.winfo_rooty()+25}')
        ttk.Label(self.window, text=self.text() if callable(self.text) else self.text, wraplength=600, padding=8).pack()

    def hide(self, event=None):
        if self.window:
            self.window.destroy()
            self.window = None
