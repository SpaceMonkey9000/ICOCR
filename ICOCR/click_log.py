"""Two-column CSV click history (marking, in_database).

0.8.4.3: rows are written (and fsynced) by one background writer thread, so a
slow disk, antivirus scan or network folder no longer stalls the window on a
click. Rows keep their click order. ``flush()`` waits for pending rows; the
application calls it on shutdown, and an ``atexit`` hook covers other exits.
Write errors are logged and collected for the UI with ``take_errors()``.
"""
import atexit
import csv
import logging
import os
import queue
import threading
import time
from pathlib import Path

FIELDS = ['marking', 'in_database']


def click_record(row, database_loaded=True):
    return {'marking': row['key'],
            'in_database': ('yes' if row.get('database_matches') else 'no') if database_loaded else 'unknown'}


def write_click(path, record):
    """Append one row synchronously (header for a new/empty file) and fsync."""
    path = Path(path)
    with path.open('a+', encoding='utf-8', newline='') as handle:
        handle.seek(0, 2)
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if handle.tell() == 0:
            writer.writeheader()
        writer.writerow(record)
        handle.flush()
        os.fsync(handle.fileno())
    return record


class ClickWriter:
    """Single background writer; started on first use, daemon, never blocks the caller."""
    def __init__(self):
        self.queue = queue.Queue()
        self.errors = queue.Queue()
        self._thread = None
        self._lock = threading.Lock()

    def submit(self, path, record):
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name='click-log', daemon=True)
                self._thread.start()
        self.queue.put((Path(path), record))

    def _run(self):
        while True:
            path, record = self.queue.get()
            try:
                write_click(path, record)
            except Exception as exc:
                logging.exception('Could not write click history to %s', path)
                self.errors.put((path, record, str(exc)))
            finally:
                self.queue.task_done()

    def pending(self):
        return self.queue.unfinished_tasks

    def flush(self, timeout=None):
        """Wait until every submitted row is written; False if the timeout expired."""
        deadline = None if timeout is None else time.monotonic() + timeout
        condition = self.queue.all_tasks_done
        with condition:
            while self.queue.unfinished_tasks:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return False
                condition.wait(remaining)
        return True

    def take_errors(self):
        errors = []
        while True:
            try:
                errors.append(self.errors.get_nowait())
            except queue.Empty:
                return errors


WRITER = ClickWriter()


def record_click(path, row, *, database_loaded=True, wait=False):
    """Queue one click row for the background writer and return the record.

    wait=True blocks until the row (and any earlier ones) is on disk and raises
    the write error, if any, as the synchronous writer did before 0.8.4.3.
    """
    record = click_record(row, database_loaded)
    if wait:
        flush()
        return write_click(path, record)
    WRITER.submit(path, record)
    return record


def flush(timeout=None):
    return WRITER.flush(timeout)


def take_errors():
    """Write failures since the last call: [(path, record, message)]."""
    return WRITER.take_errors()


atexit.register(flush, 3.)
