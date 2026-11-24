"""Open a History match in a separately installed ICDB Qt application.

No database changes; process launch is explicit and uses the same DATA directory.
"""
import os
import subprocess
import sys
from pathlib import Path


def icdb_entry(path):
    """Return the ICDB installation directory for a selected executable/script/folder."""
    selected = Path(path).expanduser().resolve()
    folder = selected if selected.is_dir() else selected.parent
    if (folder / 'icdb_qt.py').is_file() and (folder / 'run_qt_windows.bat').is_file():
        try:
            if "'--open-part'" in (folder / 'icdb_qt.py').read_text(encoding='utf-8'):
                return folder
        except OSError:
            pass
        raise ValueError('This ICDB installation does not support Open in ICDB. Use the accompanying updated ICDB build.')
    raise ValueError('Choose the updated ICDB folder containing icdb_qt.py and run_qt_windows.bat')


def launch_icdb(folder, data, part, popen=subprocess.Popen, action='open', target=None):
    folder = icdb_entry(folder)
    if action == 'add' and "'--add-part'" not in (folder / 'icdb_qt.py').read_text(encoding='utf-8'):
        raise ValueError('This ICDB version does not support Add to ICDB. Install the updated ICDB build.')
    data = Path(data).expanduser().resolve()
    if not part or not str(part).strip():
        raise ValueError('No selected ICDB match')
    if action not in ('open', 'add', 'alias'):
        raise ValueError('Unsupported ICDB action')
    option = {'open': '--open-part', 'add': '--add-part', 'alias': '--add-alias'}[action]
    if action == 'alias' and "'--add-alias'" not in (folder / 'icdb_qt.py').read_text(encoding='utf-8'):
        raise ValueError('This ICDB version does not support Add alias. Install the updated ICDB build.')
    if os.name == 'nt':
        # Invoke ICDB's own Python directly. Avoid cmd.exe parsing OCR-provided text.
        python = folder / '.venv-qt' / 'Scripts' / 'python.exe'
        if not python.is_file():
            raise FileNotFoundError(f'ICDB environment missing: {python}. Run setup_qt_windows.bat in ICDB first.')
        flags = getattr(subprocess, 'CREATE_NEW_CONSOLE', 0)
    else:
        env_python = folder / '.venv-qt' / 'bin' / 'python'
        python = env_python if env_python.is_file() else Path(sys.executable)
        flags = 0
    # Equals form: a value starting with '-' (an OCR marking, a typed part number or
    # a DATA path) must never be parsed by ICDB as another option.
    argv = [str(python), str(folder / 'icdb_qt.py'), f'--data={data}',
            f'{option}={str(part).strip()}']
    if action == 'alias':
        if target:
            argv += ['--alias-part=' + str(target.get('part') or ''),
                     '--alias-manufacturer=' + str(target.get('manufacturer') or '')]
    return popen(argv, cwd=str(folder), creationflags=flags)
