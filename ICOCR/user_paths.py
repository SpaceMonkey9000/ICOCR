"""ICOCR user configuration and first-run initialization (0.8.9.7)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = Path(os.environ.get('LOCALAPPDATA') or os.environ.get('XDG_CONFIG_HOME') or Path.home()/'.config')
CONFIG_DIR = Path(os.environ.get('ICOCR_CONFIG_DIR') or BASE/'ICSuite'/'ICOCR').expanduser().resolve()
SETTINGS_FILE = CONFIG_DIR/'settings.json'
FACTORY = ROOT/'factory'


def prepare_config(data=None):
    """Populate a fresh install without overwriting settings or installed modules."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not SETTINGS_FILE.exists():
        source = FACTORY/'settings.json'
        with SETTINGS_FILE.open('x', encoding='utf-8') as out:
            out.write(source.read_text('utf-8'))
    grouping = CONFIG_DIR/'package_groups.json'
    try:
        with grouping.open('xb') as out:
            out.write((FACTORY/'package_groups.json').read_bytes())
    except FileExistsError:
        pass
    from rule_modules import rules_directory
    destination = rules_directory()
    destination.mkdir(parents=True, exist_ok=True)
    for source in sorted((FACTORY/'rules').glob('*.json')):
        target = destination/source.name
        try:
            with target.open('xb') as out:
                out.write(source.read_bytes())
        except FileExistsError:
            pass


def _pictures_folder():
    """The user's Pictures folder, following a moved Windows Pictures location."""
    if os.name == 'nt':
        try:
            import ctypes
            import uuid
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [('Data1', wintypes.DWORD), ('Data2', wintypes.WORD),
                            ('Data3', wintypes.WORD), ('Data4', ctypes.c_ubyte * 8)]
            raw = uuid.UUID('{33E28130-4E1E-4676-835A-98395C3BC3BB}').bytes_le  # FOLDERID_Pictures
            folder_id = GUID.from_buffer_copy(raw)
            path = ctypes.c_wchar_p()
            shell32 = ctypes.windll.shell32
            if shell32.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None, ctypes.byref(path)) == 0:
                try:
                    return Path(path.value)
                finally:
                    ctypes.windll.ole32.CoTaskMemFree(path)
        except Exception:
            pass
    return Path.home() / 'Pictures'


def default_capture_directory():
    return _pictures_folder() / 'ICOCR'


def capture_directory(preferences):
    """Missing/empty folder preferences use the current user's Pictures folder."""
    value = preferences.get('capture_folder')
    if isinstance(value, str) and value.strip():
        return Path(value).expanduser().resolve()
    return default_capture_directory()
