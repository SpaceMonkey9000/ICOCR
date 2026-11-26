"""Background threads: database and OCR engine loading, and the scan worker."""
import logging
from recognition_diagnostics import begin, end, event
import threading
import traceback
from PySide6.QtCore import QThread, Signal
from body_scan import read_with_body
from ic_body_detector import detect as detect_ic_bodies, for_roi as detector_for_roi
from component_catalog import Catalog
from ocr_core import OCR, crop_roi, ScanCancelled
from project_paths import DATA
from scan_result import build_scan_result
from shared_data import database_file


_ENGINE = None
_ENGINE_ERROR = None
_ENGINE_LOCK = threading.Lock()
# Held while the engine runs. Scans are serialised by the window, but the
# background warm-up could otherwise use the same engine as the first scan.
ENGINE_IN_USE = threading.Lock()


def shared_ocr():
    """One OCR engine for the whole session.

    Creating an engine loads three ONNX models (and, on CUDA, runs the cuDNN
    algorithm search), so it must not be repeated for every scan. After a
    failure the error is raised again without reloading the models, until
    retry_engine() is called (a manual scan does that).
    """
    global _ENGINE, _ENGINE_ERROR
    with _ENGINE_LOCK:
        if _ENGINE is None:
            if _ENGINE_ERROR is not None:
                raise RuntimeError(f'OCR engine unavailable: {_ENGINE_ERROR}')
            try:
                _ENGINE = OCR()
            except Exception as exc:
                _ENGINE_ERROR = f'{type(exc).__name__}: {exc}'
                raise
        return _ENGINE


def engine_failed():
    """True when creating the OCR engine failed and was not retried since."""
    return _ENGINE is None and _ENGINE_ERROR is not None


def retry_engine():
    """Allow the next shared_ocr() call to try creating the engine again."""
    global _ENGINE_ERROR
    with _ENGINE_LOCK:
        _ENGINE_ERROR = None


class DatabaseLoader(QThread):
    loaded = Signal(object, str)

    def run(self):
        path = database_file(DATA)
        if not path.is_file():
            self.loaded.emit(None, 'No components.sqlite in shared DATA folder')
            return
        try:
            c = Catalog(path)
            self.loaded.emit(c, f'ICDB: {c.count:,} part numbers loaded')
        except Exception as exc:
            self.loaded.emit(None, f'Database error: {exc}')


class EngineLoader(QThread):
    """Loads the OCR models in the background so the first scan is not delayed."""
    failed = Signal(str)
    loaded = Signal(str)

    def run(self):
        try:
            engine = shared_ocr()
            try:
                # Pay ONNX Runtime's lazy initialisation now, not on the first scan.
                with ENGINE_IN_USE:
                    engine.warm_up()
            except Exception:
                logging.exception('OCR warm-up failed')
            self.loaded.emit(engine.runtime.get('label', ''))
        except Exception as exc:
            self.failed.emit(f'{type(exc).__name__}: {exc}')


class FullScanWorker(QThread):
    scanned = Signal(int, object, object, float, str)

    def __init__(self, epoch, frame, roi, catalog, settings, parent=None):
        super().__init__(parent)
        self.epoch = epoch
        self.frame = frame          # camera frames are never modified after capture
        self.roi = tuple(roi)
        self.catalog = catalog
        self.options = dict(settings)
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()
        self.requestInterruption()

    def run(self):
        try:
            with ENGINE_IN_USE:
                if not self.cancel_event.is_set():
                    self._trace = []
                    if self.options.get("diagnostics", False):
                        token, self._trace = begin()
                        try:
                            self._scan()
                        finally:
                            end(token)
                    else:
                        self._scan()
        finally:
            self.frame = self.catalog = None   # do not keep the frame alive with the thread object

    def _scan(self):
        try:
            event("scan_started", roi=self.roi, frame_shape=self.frame.shape)
            ocr = shared_ocr()
            ocr.fast = self.options['fast']
            ocr.targeted_original = self.options['targeted']
            ocr.verification = False
            ocr.acquisition_only = False
            ocr.preprocessing = None
            ocr.cancelled = self.cancel_event.is_set
            crop = crop_roi(self.frame, self.roi)
            if self.cancel_event.is_set():
                return
            model_detections = []
            model_error = None
            if (self.options['body'] or self.options.get('body_only')) and self.options.get('body_model'):
                try:
                    model_detections = detect_ic_bodies(
                        self.frame, self.options['body_model'],
                        cancelled=self.cancel_event.is_set)
                except Exception as exc:
                    model_error = f'{type(exc).__name__}: {exc}'
            event("component_detection", detections=len(model_detections), error=model_error, outlines=[d["polygon"] for d in model_detections])
            package_options = dict(enabled=self.options['package'],
                                   model=self.options['package_model'], confidence=.5)
            if self.options.get('multi'):
                from multi_chip import read_chips
                chips, summary = read_chips(
                    ocr, crop, read=read_with_body, auto_body=self.options['body'],
                    cancelled=self.cancel_event.is_set, catalog=self.catalog,
                    preferred='Original', known=(), live=False,
                    package_options=package_options, package_frame=self.frame,
                    detections=model_detections, detector_only=bool(self.options.get('body_only')),
                    offset=(int(self.roi[0]*self.frame.shape[1]),int(self.roi[1]*self.frame.shape[0])))
                if self.cancel_event.is_set():
                    return
                rows = [c['target'] for c in chips if c.get('target')]
                diagnostics = dict(
                    model_body_outlines=[d['polygon'] for d in model_detections],
                    overlay_chips=[dict(target=c.get('target'), body_box=c.get('body_box'),
                                        status=c.get('status')) for c in chips],
                    multi_chip=summary,
                    body_model_error=model_error, body_model_detections=len(model_detections),
                    detector_only=bool(self.options.get('body_only')),
                    chips=[dict(index=c['index'], status=c['status'], region=c['region'],
                                error=c.get('error')) for c in chips])
                if self.options.get("diagnostics", False):
                    diagnostics["chip_diagnostics"] = [dict(index=c["index"], status=c["status"], region=c["region"], error=c.get("error"), diagnostics=c["diagnostics"]) for c in chips]
                decision = build_scan_result(rows, rows, self.catalog)
                elapsed = summary['total_ms'] / 1000.0
            else:
                # Body-only limits the OCR input, independently of scan scope.
                # In single-chip mode, one model body is selected; no full-frame
                # OCR or geometric fallback is permitted if detection fails.
                chosen_body = detector_for_roi(model_detections, self.roi, self.frame.shape)
                if self.options.get('body_only') and chosen_body is None:
                    rows, elapsed = [], 0.0
                    diagnostics = dict(body_detection=dict(status='not_found'),
                                       all_candidates=[], scan_result=build_scan_result([], [], self.catalog),
                                       scan_input=dict(requested='model body', actual='no OCR',
                                                       reason='No detected IC body within scan region'))
                else:
                    rows, elapsed = read_with_body(
                        ocr, crop, enabled=self.options['body'] or self.options.get('body_only'),
                        detection=chosen_body,
                        allow_recovery=not self.options.get('body_only'),
                        preferred='Original', known=(), catalog=self.catalog, live=False,
                        package_options=package_options,
                        package_frame=self.frame, package_roi=self.roi)
                    diagnostics = dict(ocr.last_diagnostics or {})
                diagnostics['body_model_error'] = model_error
                diagnostics['body_model_detections'] = len(model_detections)
                diagnostics['model_body_outlines'] = [d['polygon'] for d in model_detections]
                decision = diagnostics.get('scan_result') or build_scan_result(
                    rows, diagnostics.get('all_candidates', rows), self.catalog)
            if not self.cancel_event.is_set():
                event("scan_finished", selected=(decision.get("selected") or {}).get("key"))
                if self.options.get("diagnostics", False):
                    diagnostics["execution_trace"] = self._trace
                    diagnostics["scan_settings"] = dict(self.options)
                self.scanned.emit(self.epoch, decision, diagnostics, float(elapsed), '')
        except ScanCancelled:
            return
        except Exception:
            if not self.cancel_event.is_set():
                self.scanned.emit(self.epoch, None, {"execution_trace": self._trace}, 0.0, traceback.format_exc())
