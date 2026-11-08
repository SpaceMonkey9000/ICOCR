"""DATA paths, logging set-up and the one-time click-log migration.

Before 0.8.4.8 importing app.py created folders, configured logging and wrote to
the log. These now run from ``app.main()`` / ``App.__init__`` only.
"""
import csv
import json
import logging
import logging.handlers
import time

from config_loader import configuration_diagnostics
from project_paths import DATA, ROOT

# User data lives outside the version folder so it survives upgrades.
CLICK_LOG = DATA/'marking_clicks.csv'
LOG_FILE = DATA/'ICOCR.log'
SESSION = time.strftime('%Y%m%d%H%M%S')   # identifies scans in confirmed.csv


def prepare_data_folder():
    DATA.mkdir(parents=True, exist_ok=True)
    for folder in ('models', 'pinouts'):
        (DATA/folder).mkdir(exist_ok=True)


LOG_BYTES = 5*1024*1024   # ICOCR.log rotates at 5 MB and keeps 3 old files (0.8.8)
LOG_BACKUPS = 3


def configure_logging():
    handler = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=LOG_BYTES, backupCount=LOG_BACKUPS,
                                                   encoding='utf-8', delay=True)
    logging.basicConfig(handlers=[handler], level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    logging.info('Startup configuration: %s', json.dumps(configuration_diagnostics()))


def legacy_click_logs(root=ROOT):
    """Click logs written beside app.py by this or sibling pre-0.7.7.2 folders."""
    found = [root/'marking_clicks.csv'] + sorted(root.parent.glob('ICOCR*/marking_clicks.csv'))
    unique, seen = [], set()
    for path in found:
        try:
            if path.is_file() and path.stat().st_size and path.resolve() not in seen:
                seen.add(path.resolve())
                unique.append(path)
        except OSError:
            pass
    return sorted(unique, key=lambda path: path.stat().st_mtime)


def migrate_click_log(sources=None, target=CLICK_LOG):
    """Merge old per-version click logs once, oldest first; never touch an existing log."""
    try:
        if target.exists():
            return 0
        sources = legacy_click_logs() if sources is None else sources
        rows = []
        for source in sources:
            with open(source, encoding='utf-8', newline='') as handle:
                rows += [row for row in csv.DictReader(handle) if row.get('marking')]
        if not rows:
            return 0
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix('.tmp')
        with open(temporary, 'w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=['marking', 'in_database'], extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(target)
        logging.info('Merged %d click rows from %s into %s', len(rows), [str(s) for s in sources], target)
        return len(rows)
    except (OSError, csv.Error):
        logging.exception('Click log migration failed')
        return 0
