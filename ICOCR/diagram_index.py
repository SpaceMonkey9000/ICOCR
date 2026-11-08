"""JPEG metadata index. No pixel decoding or directory traversal during lookup."""
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
from contextlib import closing
from PIL import Image
from project_paths import DATA


def package_key(value):
    return re.sub(r'[\s_-]+', '', str(value or '')).upper()


def filename_key(path):
    fields = path.stem.upper().split('__')
    if len(fields) > 2 or not re.fullmatch(r'[A-Z0-9][A-Z0-9+.-]{1,79}', fields[0]):
        return None
    package = package_key(fields[1]) if len(fields) == 2 else ''
    if len(fields) == 2 and not re.fullmatch(r'[A-Z0-9]{2,40}', package):
        return None
    return fields[0], package


class DiagramIndex:
    # Background polling: check directory mtimes every ACTIVE_INTERVAL seconds
    # after a change, back off to IDLE_INTERVAL while nothing changes, and walk
    # every file at least every FULL_WALK_INTERVAL (a JPEG overwritten in place
    # does not change its directory's mtime). refresh() always walks at once.
    ACTIVE_INTERVAL = 5
    IDLE_INTERVAL = 30
    FULL_WALK_INTERVAL = 60

    def __init__(self, folder, cache_dir=None):
        self.folder = Path(folder).expanduser().resolve()
        token = hashlib.sha256(str(self.folder).encode()).hexdigest()[:24]
        self.database = Path(cache_dir or DATA / 'diagram_index') / (token + '.sqlite')
        self.records = {}
        self.by_device = {}
        self.devices = frozenset()
        self.generation = 0
        self.status = 'Indexing JPEG folder…'
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._forced = False
        self._signature = None
        self._thread = None

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True, name='diagram-index')
            self._thread.start()

    def close(self):
        self._stop.set()
        self._wake.set()

    def refresh(self):
        """Explicit "Refresh diagram index": full walk immediately."""
        self._forced = True
        self._wake.set()

    def directory_signature(self):
        """(relative dir, mtime_ns) for the folder and every non-symlink subfolder.

        Adding, removing or renaming a file changes its directory's mtime;
        overwriting a file in place does not (covered by the periodic full walk).
        """
        signature = []
        pending = [self.folder]
        while pending:
            directory = pending.pop()
            signature.append((str(directory), os.stat(directory).st_mtime_ns))
            with os.scandir(directory) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(Path(entry.path))
        return tuple(sorted(signature))

    def _poll(self, now, last_walk):
        """One background step; returns (walked, changed)."""
        forced, self._forced = self._forced, False
        try:
            signature = self.directory_signature()
        except OSError:
            signature = None
        if (not forced and signature is not None and signature == self._signature and
                last_walk is not None and now - last_walk < self.FULL_WALK_INTERVAL):
            return False, False
        before = (self.generation, self.status)
        try:
            self.scan()
            self._signature = signature
        except Exception as exc:
            self._signature = None
            self._publish({}, 'Diagram index unavailable: ' + str(exc))
        return True, (self.generation, self.status) != before

    def _run(self):
        last_walk = None
        interval = self.ACTIVE_INTERVAL
        while not self._stop.is_set():
            self._wake.clear()
            now = time.monotonic()
            walked, changed = self._poll(now, last_walk)
            if walked:
                last_walk = now
            if changed:
                interval = self.ACTIVE_INTERVAL
            elif walked or interval == self.ACTIVE_INTERVAL:
                interval = self.IDLE_INTERVAL
            self._wake.wait(interval)

    def _publish(self, records, status):
        """Publish a completed snapshot; bump generation only on a real change."""
        if records != self.records or status != self.status:
            if records != self.records:
                by_device = {}
                for (device, package), entries in records.items():
                    by_device.setdefault(device, []).extend((package, entry) for entry in entries)
                self.by_device = by_device
                self.devices = frozenset(key[0] for key in records)
                self.records = records  # readers never see partial scans
            self.status = status
            self.generation += 1

    def scan(self):
        self.database.parent.mkdir(parents=True, exist_ok=True)
        if not self.folder.is_dir():
            raise OSError('Folder unavailable: ' + str(self.folder))
        with closing(sqlite3.connect(self.database, timeout=2)) as connection, connection as db:
            db.execute('CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, device TEXT, package TEXT, mtime INTEGER, size INTEGER, valid INTEGER)')
            db.execute('CREATE INDEX IF NOT EXISTS device_package ON files(device, package)')
            old = {r[0]: r for r in db.execute('SELECT * FROM files')}
            seen = set()
            records = {}
            invalid = 0
            def walk_error(exc):
                raise exc
            for directory, dirs, names in os.walk(self.folder, onerror=walk_error, followlinks=False):
                dirs[:] = [d for d in dirs if not (Path(directory)/d).is_symlink()]
                for name in names:
                    if self._stop.is_set():
                        return
                    path = Path(directory)/name
                    if path.suffix.lower() not in ('.jpg', '.jpeg') or path.is_symlink():
                        continue
                    key = filename_key(path)
                    if key is None:
                        invalid += 1
                        continue
                    relative = str(path.relative_to(self.folder))
                    try:
                        stat = path.stat()
                    except FileNotFoundError:
                        continue
                    seen.add(relative)
                    previous = old.get(relative)
                    if previous and previous[3:5] == (stat.st_mtime_ns, stat.st_size):
                        valid = previous[5]
                    else:
                        try:
                            with Image.open(path) as im:
                                valid = int(im.format == 'JPEG' and im.width * im.height <= 24000000)
                        except (OSError, ValueError, Image.DecompressionBombError):
                            valid = 0
                        db.execute('INSERT OR REPLACE INTO files VALUES (?, ?, ?, ?, ?, ?)',
                                   (relative, *key, stat.st_mtime_ns, stat.st_size, valid))
                    if not valid:
                        invalid += 1
                        continue
                    records.setdefault(key, []).append(dict(path=path, device=key[0],
                        package=key[1] or 'General reference; package unspecified',
                        source='User-added JPEG', orientation='unspecified', verified=False,
                        stamp=(stat.st_mtime_ns, stat.st_size)))
            db.executemany('DELETE FROM files WHERE path=?', [(name,) for name in old.keys()-seen])
        count = sum(len(rows) for rows in records.values())
        duplicates = sum(len(rows)>1 for rows in records.values())
        self._publish(records, f'{count} JPEGs indexed; {duplicates} duplicate keys; {invalid} skipped')

    def find(self, device, package=''):
        records = self.records
        package = package_key(package)
        choices = records.get((device, package), []) if package else []
        if choices:
            return (choices[0], '') if len(choices) == 1 else (None, 'Duplicate device/package diagrams')
        general = records.get((device, ''), [])
        if general:
            return (general[0], '') if len(general) == 1 else (None, 'Duplicate device diagrams')
        if device in self.devices:
            return None, 'No diagram for this package' if package else 'Package required for diagram'
        return None, 'Logic diagram unavailable'
