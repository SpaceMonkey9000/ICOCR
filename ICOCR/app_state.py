"""DATA folders and logging set-up.

Before 0.8.4.8 importing app.py created folders, configured logging and wrote to
the log. These now run from ``app.main()`` / ``App.__init__`` only.
"""
import json
import logging
import logging.handlers

from config_loader import configuration_diagnostics
from project_paths import DATA

# User data lives outside the version folder so it survives upgrades.
LOG_FILE = DATA/'ICOCR.log'


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
