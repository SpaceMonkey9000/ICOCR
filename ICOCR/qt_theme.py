"""Native Qt Fusion styling matching ICDB Revision 9/11.

Only presentation code lives here. No recognition, camera or database logic.
"""
import sys
from PySide6.QtGui import QPalette, QColor

THEMES = {'light': 'Light', 'dark': 'Dark graphite'}
LEGACY_DARK = frozenset(('dark', 'graphite', 'slate'))

def normalized_theme(value):
    """Migrate six-theme ICOCR preferences to the two original ICDB themes."""
    return 'dark' if value in LEGACY_DARK else 'light'

def is_dark(theme):
    return normalized_theme(theme) == 'dark'

def viewport_background(theme):
    return '#25282E' if is_dark(theme) else '#FFFFFF'

def apply_palette(application, dark=False):
    """Set a complete application palette including input fields and tooltips."""
    palette = QPalette()
    if dark:
        colors = {
            QPalette.ColorRole.Window: '#30343B',
            QPalette.ColorRole.WindowText: '#ECEFF2',
            QPalette.ColorRole.Base: '#25282E',
            QPalette.ColorRole.AlternateBase: '#343941',
            QPalette.ColorRole.Text: '#ECEFF2',
            QPalette.ColorRole.Button: '#404650',
            QPalette.ColorRole.ButtonText: '#ECEFF2',
            QPalette.ColorRole.Highlight: '#516C8B',
            QPalette.ColorRole.HighlightedText: '#FFFFFF',
            QPalette.ColorRole.ToolTipBase: '#25282E',
            QPalette.ColorRole.ToolTipText: '#ECEFF2',
            QPalette.ColorRole.PlaceholderText: '#9CA5B0',
        }
    else:
        colors = {
            QPalette.ColorRole.Window: '#F0F0F0',
            QPalette.ColorRole.WindowText: '#171717',
            QPalette.ColorRole.Base: '#FFFFFF',
            QPalette.ColorRole.AlternateBase: '#F6F6F6',
            QPalette.ColorRole.Text: '#171717',
            QPalette.ColorRole.Button: '#E6E6E6',
            QPalette.ColorRole.ButtonText: '#171717',
            QPalette.ColorRole.Highlight: '#3478B8',
            QPalette.ColorRole.HighlightedText: '#FFFFFF',
            QPalette.ColorRole.ToolTipBase: '#FFFFDC',
            QPalette.ColorRole.ToolTipText: '#171717',
            QPalette.ColorRole.PlaceholderText: '#777777',
        }
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    application.setPalette(palette)


def use_dark_windows_titlebar(widget):
    """Set a dark native Win10/11 title bar without replacing Qt Fusion chrome.

    This is an OS-level preference, not a custom title bar. Unsupported
    platforms/Windows builds leave their native title bars unchanged.
    """
    if sys.platform != 'win32':
        return False
    try:
        import ctypes
        from ctypes import wintypes
        hwnd = wintypes.HWND(int(widget.winId()))
        value = ctypes.c_int(1)
        dwm = ctypes.windll.dwmapi.DwmSetWindowAttribute
        dark_mode = False
        for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE
            if dwm(hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                dark_mode = True
                break
        # Windows 11 supports explicit native caption/text colours. Older
        # builds reject these attributes and keep the immersive-dark fallback.
        caption = wintypes.DWORD(0x003B3430)  # COLORREF #30343B
        title_text = wintypes.DWORD(0x00FFFFFF)
        caption_ok = dwm(hwnd, 35, ctypes.byref(caption), ctypes.sizeof(caption)) == 0
        dwm(hwnd, 36, ctypes.byref(title_text), ctypes.sizeof(title_text))
        return dark_mode or caption_ok
    except (AttributeError, OSError, ValueError):
        pass
    return False

