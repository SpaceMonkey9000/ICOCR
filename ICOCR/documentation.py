"""Confirmed readings and clean captures; no OCR decisions are changed.

0.8.3.8: the per-scan encounter log is replaced. A record is written only when
the technician clicks a reading (or edits one): that click confirms the text.
Each confirmation saves the scan snapshot as JPEG and one CSV row.

0.8.8: writes run on one daemon thread fed by a queue (as ``click_log``), so a
save stuck on a slow or unreachable folder can no longer keep the process alive
after the window has closed. Requests are written in submission order.
"""
import csv
import io
from datetime import datetime, timezone
from pathlib import Path
import queue
import threading
import cv2


def stamp():
    return datetime.now(timezone.utc).isoformat()


def json_default(value):
    if hasattr(value, 'tolist'):
        return value.tolist()
    if hasattr(value, 'item'):
        return value.item()
    raise TypeError(type(value).__name__)


class Documentation:
    """One bounded background writer. Accepted writes drain on normal shutdown.

    Every accepted request produces exactly one ``(kind, path, error)`` event, in
    submission order; a request refused because the queue is full produces one
    event whose error is :attr:`QUEUE_FULL` (and ``_submit`` returns False).
    """
    QUEUE_FULL = 'Save queue full; image was not saved'

    def __init__(self, directory):
        self.directory = Path(directory)
        self.events = queue.Queue()
        self.jobs = queue.Queue()
        self.slots = threading.BoundedSemaphore(4)
        self.sequence = 0
        self.closed = False
        self._thread = None
        self._lock = threading.Lock()

    def _submit(self, kind, function, *args):
        if not self.slots.acquire(blocking=False):
            self.events.put((kind, None, self.QUEUE_FULL))
            return False
        with self._lock:
            if self.closed:
                self.slots.release()
                raise RuntimeError('Documentation writer is closed')
            if self._thread is None:
                # Daemon: never joined at interpreter exit (close() is bounded).
                self._thread = threading.Thread(target=self._worker, name='documentation', daemon=True)
                self._thread.start()
            self.jobs.put((kind, function, args))
        return True

    def _worker(self):
        while True:
            job = self.jobs.get()
            if job is None:
                return
            self._run(*job)

    def _run(self, kind, function, args):
        try:
            self.events.put((kind, function(*args), None))
        except Exception as exc:
            self.events.put((kind, None, str(exc)))
        finally:
            self.slots.release()

    def capture(self, frame):
        return self._submit('capture', self._capture, frame.copy())

    @staticmethod
    def _jpeg(image, quality):
        ok, encoded = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
        if not ok:
            raise OSError('JPEG encoding failed')
        return encoded.tobytes()

    CAPTURE_JPEG_QUALITY = 95

    def _capture(self, frame):
        """Full-resolution capture as JPEG quality 95 (0.8.3.5; was lossless PNG).
        Numbering continues across older PNG captures; no name is reused."""
        directory = self.directory / 'captures'
        directory.mkdir(parents=True, exist_ok=True)
        encoded = self._jpeg(frame, self.CAPTURE_JPEG_QUALITY)
        if self.sequence == 0:
            self.sequence = max((int(p.stem[3:]) for p in directory.glob('IC_*')
                                 if p.suffix.lower() in ('.png', '.jpg', '.jpeg') and p.stem[3:].isdigit()),
                                default=0)
        while True:
            self.sequence += 1
            if any((directory / f'IC_{self.sequence:06d}{ext}').exists() for ext in ('.png', '.jpeg')):
                continue
            path = directory / f'IC_{self.sequence:06d}.jpg'
            try:
                stream = path.open('xb')  # collision safe across processes/restarts
            except FileExistsError:
                continue
            try:
                with stream:
                    stream.write(encoded)
            except Exception:
                path.unlink(missing_ok=True)
                raise
            return path

    CONFIRMED_DIR = 'confirmed'
    CONFIRMED_CSV = 'confirmed.csv'
    SNAPSHOT_JPEG_QUALITY = 95
    FIELDS = ['time', 'image', 'part_number', 'confirmed_text', 'database_match',
              'corrected', 'correction', 'ocr_text', 'automatic_pick', 'all_readings',
              'mode', 'chip', 'scan', 'database']

    def confirm(self, snapshot, fields):
        """Save one technician-confirmed reading (background; reported via events)."""
        row = {name: fields.get(name, '') for name in self.FIELDS if name not in ('time', 'image')}
        return self._submit('confirm', self._confirm, snapshot.copy(), row,
                            datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    def _confirm(self, snapshot, row, when):
        directory = self.directory / self.CONFIRMED_DIR
        directory.mkdir(parents=True, exist_ok=True)
        encoded = self._jpeg(snapshot, self.SNAPSHOT_JPEG_QUALITY)
        number = max((int(p.stem[2:]) for p in directory.glob('C_*.jpg') if p.stem[2:].isdigit()),
                     default=0)
        while True:
            number += 1
            path = directory / f'C_{number:06d}.jpg'
            try:
                stream = path.open('xb')   # never overwrite, also across restarts
            except FileExistsError:
                continue
            try:
                with stream:
                    stream.write(encoded)
            except Exception:
                path.unlink(missing_ok=True)
                raise
            break
        index = directory / self.CONFIRMED_CSV
        record = dict(row, time=when, image=path.name)
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=self.FIELDS, extrasaction='ignore')
        try:
            new = not index.exists() or index.stat().st_size == 0
            if new:
                writer.writeheader()
            writer.writerow(record)
            # utf-8-sig (BOM) only at the start, so Excel opens it with the right encoding.
            with open(index, 'a', encoding='utf-8-sig' if new else 'utf-8', newline='') as handle:
                handle.write(buffer.getvalue())
        except Exception as exc:
            # 0.8.8: no JPEG without its CSV row; the technician can simply retry.
            path.unlink(missing_ok=True)
            if isinstance(exc, PermissionError):
                raise OSError(f'{self.CONFIRMED_CSV} is open in another program (close Excel); '
                              'the reading was not logged') from exc
            raise
        return path

    def close(self, timeout=None):
        """Write every accepted request, then stop the writer thread.

        Returns False when writes are still running after ``timeout`` seconds;
        the daemon thread is then abandoned and does not delay process exit.
        """
        with self._lock:
            self.closed = True
            thread = self._thread
            if thread is None:
                return True
            self.jobs.put(None)
        thread.join(timeout)
        return not thread.is_alive()
