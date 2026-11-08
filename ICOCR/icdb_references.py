"""Read-only ICDB 0.4 reference snapshots. All file/SQLite work runs off the UI thread."""
import logging
import re
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path, PureWindowsPath


def package_key(value):
    return re.sub(r'[\s_-]+', '', str(value or '')).upper()


def identity(match):
    return (str(match.get('part') or '').strip().upper(),
            str(match.get('manufacturer') or '').strip().upper())


class ReferenceIndex:
    INTERVAL = 5
    FULL_INTERVAL = 30

    def __init__(self, source=None):
        self.source = Path(source).expanduser().resolve() if source else None
        self.snapshot = ({}, frozenset(), 'No ICDB reference source', 0)
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = None
        self._signature = None
        self._last_scan = 0
        self._forced = False
        self._logged_problems = ''

    @property
    def records(self): return self.snapshot[0]
    @property
    def status(self): return self.snapshot[2]
    @property
    def generation(self): return self.snapshot[3]

    def start(self):
        if self.source and self._thread is None:
            self._thread = threading.Thread(target=self._run,daemon=True,name='icdb-references')
            self._thread.start()

    def close(self):
        self._stop.set();self._wake.set()

    def refresh(self):
        self._forced = True;self._wake.set()

    def _publish(self, records, status):
        old = self.snapshot
        if records != old[0] or status != old[2]:
            self.snapshot = (records, frozenset(k[0] for k in records), status, old[3]+1)

    def _run(self):
        while not self._stop.is_set():
            self._wake.clear()
            self.poll()
            self._wake.wait(self.INTERVAL)

    def signature(self):
        result = []
        for path in (self.source, Path(str(self.source)+'-wal')):
            try:
                stat = path.stat();result.append((stat.st_mtime_ns,stat.st_size))
            except FileNotFoundError:result.append(None)
        # 0.8.8: a reset WAL can be rewritten at the same size within one
        # filesystem timestamp tick; its header salt changes on every reset.
        try:
            with open(str(self.source)+'-wal','rb') as wal:result.append(wal.read(32))
        except OSError:result.append(None)
        return tuple(result)

    def poll(self):
        now = time.monotonic()
        try:
            signature = self.signature()
            if not self._forced and signature == self._signature and now-self._last_scan < self.FULL_INTERVAL:
                return
            self._forced = False
            self.scan()
            self._signature = signature;self._last_scan = now
        except Exception as exc:
            self._signature = None
            self._publish({}, 'ICDB references unavailable: '+str(exc))

    def _read(self):
        with closing(sqlite3.connect(self.source.as_uri()+'?mode=ro',uri=True,timeout=2)) as db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')  # assets and associations must be one consistent snapshot
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {'pinout_assets','pinout_links'}.issubset(tables):
                return [], []
            assets = [dict(r) for r in db.execute('SELECT * FROM pinout_assets')]
            links = [dict(r) for r in db.execute('''SELECT l.*,c.part_number,c.manufacturer
                FROM pinout_links l JOIN components c ON c.id=l.component_id ORDER BY l.id''')]
            return assets, links

    def scan(self):
        if self.source is None:
            self._publish({},'No ICDB reference source');return
        assets, links = self._read()
        # 0.8.8: an invalid row is skipped and counted; it no longer blanks
        # every reference. A duplicated asset ID is ambiguous, so that ID is dropped.
        root = self.source.parent.parent if self.source.parent.name == 'db' else self.source.parent
        pinouts = (root/'pinouts').resolve()
        by_id = {};asset_ids = set();duplicates = set();problems = []
        for asset in assets:
            if asset['id'] in asset_ids:
                duplicates.add(asset['id']);continue
            asset_ids.add(asset['id'])
            reason = self._asset_problem(asset, root, pinouts)
            if reason:
                problems.append(f'image {asset["id"]!r}: {reason}')
                continue
            path = (root/Path(str(asset['path']).replace('\\','/'))).resolve()
            try:
                stat = path.stat();stamp = (stat.st_mtime_ns,stat.st_size)
            except FileNotFoundError:stamp = None
            by_id[asset['id']] = (asset,path,stamp)
        for duplicate in duplicates:
            by_id.pop(duplicate, None)
            problems.append(f'image {duplicate!r}: duplicate image ID')
        records = {};seen = set();missing = set();used = 0
        for link in links:
            if link['id'] in seen:
                problems.append(f'reference {link["id"]!r}: duplicate reference ID');continue
            seen.add(link['id'])
            part = str(link['part_number'] or '').strip().upper()
            if link['asset_id'] not in by_id or not part:
                problems.append(f'reference {link["id"]!r}: ' +
                                ('no device name' if part else 'unknown or invalid image'))
                continue
            asset,path,stamp = by_id[link['asset_id']]
            manufacturer = str(link.get('manufacturer') or '').strip().upper()
            if stamp is None:missing.add(asset['id'])
            used += 1
            records.setdefault((part,manufacturer), []).append(dict(
                reference_id='icdb:'+str(link['id']), path=path, device=part,
                manufacturer=manufacturer, package=str(link.get('package') or ''),
                pin_count=link.get('pin_count'), label=str(link.get('label') or ''),
                caption=str(asset.get('caption') or ''), source=str(asset.get('source') or 'ICDB reference'),
                is_default=bool(link.get('is_default')), verified=False, stamp=stamp,
                origin='ICDB', orientation='unspecified'))
        for rows in records.values():
            rows.sort(key=lambda r:(not r['is_default'],r['package'],r['label'],r['reference_id']))
        status = f'ICDB: {used} references for {len(records)} devices'
        if missing:status += f'; {len(missing)} missing image(s) — keep DATA/pinouts beside components.sqlite'
        summary = '; '.join(problems[:10]) + ('; ...' if len(problems) > 10 else '')
        if problems:
            status += f'; {len(problems)} invalid row(s) skipped'
            if summary != self._logged_problems:   # once per change, not every poll
                logging.warning('ICDB references: skipped %d invalid row(s): %s', len(problems), summary)
        self._logged_problems = summary
        self._publish(records,status)

    @staticmethod
    def _asset_problem(asset, root, pinouts):
        """Why an asset row cannot be used, or ''. Rejects foreign-platform
        absolute paths, local traversal and anything outside the pinouts folder."""
        raw = str(asset.get('path') or '').replace('\\','/')
        if not raw:
            return 'no image path'
        relative = Path(raw)
        if relative.is_absolute() or PureWindowsPath(raw).drive or '..' in relative.parts:
            return 'unsafe image path'
        if not (root/relative).resolve().is_relative_to(pinouts):
            return 'image must be inside the pinouts folder'
        return ''

    def choices(self, match):
        records,parts,_,_ = self.snapshot
        key = identity(match)
        rows = records.get(key, [])
        if rows:return list(rows),''
        if key[0] in parts:return [],'No ICDB reference for this manufacturer / source group'
        return [],''
