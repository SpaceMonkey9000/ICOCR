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
