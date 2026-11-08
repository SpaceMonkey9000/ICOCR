"""One capture worker owns the device. Only its latest frame is retained.

The application joins this thread (with a timeout) on exit so that
cap.release() in run() executes before the process ends (0.8.4.3).
"""
import threading
import time
import cv2


class Capture(threading.Thread):
    def __init__(self, index, backend, width, height, fps, mjpg):
        super().__init__(daemon=True)
        self.params = index, backend, width, height, fps, mjpg
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.latest = None
        self.seq = 0
        self.timestamp = 0
        self.status = 'Opening capture device…'

    def snapshot(self):
        with self.lock:
            return self.latest, self.seq, self.timestamp, self.status

    def run(self):
        index, backend, width, height, fps, mjpg = self.params
        cap = None
        try:
            cap = cv2.VideoCapture(index, backend)
            if not cap.isOpened():
                raise RuntimeError('Cannot open device. Close OBS and try another device/backend.')
            if mjpg:
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            cap.set(cv2.CAP_PROP_FPS, fps)
            # 0.8.4.3: the driver FPS is read once; querying it per frame is a
            # driver round trip (DirectShow/MSMF) on every captured frame.
            driver_fps = cap.get(cv2.CAP_PROP_FPS)
            failures = 0
            shape = None
            status = None
            while not self.stop_event.is_set():
                ok, frame = cap.read()
                if not ok:
                    failures += 1
                    if failures > 30:
                        raise RuntimeError('No frames received. Check HDMI, resolution and device selection.')
                    time.sleep(.05)
                    continue
                failures = 0
                if frame.shape[:2] != shape:
                    shape = frame.shape[:2]
                    status = f'{shape[1]} × {shape[0]} received | driver FPS {driver_fps:g}'
                with self.lock:
                    self.latest = frame
                    self.seq += 1
                    self.timestamp = time.monotonic()
                    self.status = status
        except Exception as exc:
            with self.lock:
                self.latest = None
                self.status = str(exc)
        finally:
            if cap is not None:
                cap.release()
