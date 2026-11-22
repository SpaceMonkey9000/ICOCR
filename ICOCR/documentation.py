"""Clean full-resolution captures written on a background thread.

0.8.8: writes run on one daemon thread fed by a queue, so a save stuck on a
slow or unreachable folder can no longer keep the process alive after the
window has closed. Requests are written in submission order.
"""
from pathlib import Path
import queue
import threading
import cv2

from user_paths import default_capture_directory


class Documentation:
    """One bounded background writer. Accepted writes drain on normal shutdown.

    Every accepted request produces exactly one ``(kind, path, error)`` event, in
    submission order; a request refused because the queue is full produces one
    event whose error is :attr:`QUEUE_FULL` (and ``_submit`` returns False).
    """
    QUEUE_FULL = 'Save queue full; image was not saved'

    def __init__(self, directory, capture_directory=None):
        self.directory = Path(directory)
        self.capture_directory = Path(capture_directory) if capture_directory is not None else default_capture_directory()
        self.events = queue.Queue()
        self.jobs = queue.Queue()
        self.slots = threading.BoundedSemaphore(4)
        self.sequence = 0
        self._numbered = set()     # capture folders whose existing numbers were read
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
        # Freeze the destination now; a settings change must not redirect queued saves.
        # Frames are never modified after capture, so no copy is needed here.
        return self._submit('capture', self._capture, frame, self.capture_directory)

    @staticmethod
    def _jpeg(image, quality):
        ok, encoded = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
        if not ok:
            raise OSError('JPEG encoding failed')
        return encoded.tobytes()

    CAPTURE_JPEG_QUALITY = 95

    def _capture(self, frame, directory=None):
        """Full-resolution capture as JPEG quality 95 (0.8.3.5; was lossless PNG).
        Numbering continues across older PNG captures; no name is reused."""
        directory = Path(directory) if directory is not None else self.capture_directory
        directory.mkdir(parents=True, exist_ok=True)
        encoded = self._jpeg(frame, self.CAPTURE_JPEG_QUALITY)
        key = str(directory.resolve())
        if key not in self._numbered:
            # Read the folder once; afterwards numbers continue from memory and
            # the exclusive create below still guards against other writers.
            self.sequence = max((int(p.stem[3:]) for p in directory.glob('IC_*')
                                 if p.suffix.lower() in ('.png', '.jpg', '.jpeg') and p.stem[3:].isdigit()),
                                default=0)
            self._numbered = {key}
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
