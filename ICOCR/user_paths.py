"""ICOCR user configuration and first-run initialization (0.8.9.7)."""
import json
import os
import shutil
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


def default_capture_directory():
    """Pictures/ICOCR, respecting redirected Windows Pictures folders."""
    pictures = Path.home() / 'Pictures'
    if os.name == 'nt':
        try:
            import ctypes
            buffer = ctypes.create_unicode_buffer(32768)
            # CSIDL_MYPICTURES; query only, create the ICOCR folder on first save.
            if ctypes.windll.shell32.SHGetFolderPathW(None, 0x27, None, 0, buffer) == 0 and buffer.value:
                pictures = Path(buffer.value)
        except (AttributeError, OSError):
            pass
    return pictures / 'ICOCR'


def capture_directory(preferences):
    """Missing/empty folder preferences use the current user's Pictures folder."""
    value = preferences.get('capture_folder')
    if isinstance(value, str) and value.strip():
        return Path(value).expanduser().resolve()
    return default_capture_directory()
