"""Scan requests (Tk thread), the OCR worker thread and the handling of its results.

Thread rules: ``ocr_worker``, ``read_multi``, ``multi_detections`` and
``detector_body_for`` run on the OCR thread and only read plain attributes
(epoch, closing, *_mode flags) and thread-safe workers. Everything else runs on
the Tk thread.
"""
import json
import logging
import queue
import time

import multi_chip
from app_presenters import runtime_text
from body_scan import geometric_fallback, read_with_body
from config_loader import tuning
import ic_detector
from ocr_core import OCR, ScanCancelled, crop_roi
from scan_messages import (DetectorBody, MultiRequest, MultiResult, RefineRequest, RefineResult,
                           ScanRequest, ScanResultMsg, as_request, as_result)
from scan_result import build_scan_result

MIN_CROP = 12   # pixels


class ScanningMixin:
    # ----------------------------------------------------------- Tk thread: requests
    def scan(self, live=None, observation=None, verification=False):
        if live is not True:
            self.wake_for_action()
        elif self.idle_sleep.sleeping:
            return
        if self.busy or self.drag or self.tracking_pending is not None or self.closing.is_set() or self.tasks.full():
            return
        # 0.8.3.7: multi-chip mode reads every chip in the selection from one
        # frozen frame. Enter/Scan only; Live recognition stays single-chip.
        multi = bool(self.multi_mode and observation is None and live is not True)
        if multi:
            live = False
        if live is None:
            live = self.live.get()
            self.rescan_policy.reset()
            self.observation_policy.reset()
        scan_frame = observation.frame if observation is not None else self.frame
        scan_frame_id = observation.frame_id if observation is not None else self.frame_id
        if scan_frame is None:
            return
        crop = crop_roi(scan_frame, self.roi)   # a copy: the camera keeps writing frames
        if min(crop.shape[:2]) < MIN_CROP:
            self.ocr_state.set('Select a larger region.')
            return
        # 0.8.4.3: the snapshot and the OCR request share this crop. Nothing writes
        # to either (OCR, preview and confirmed-reading writers only read it).
        # 0.8.8: the snapshot belongs to the readings it produced. A scan that
        # clears the list shows it at once; a Live scan (also a verification
        # scan) shows it only when its result replaces the displayed one.
        shot = dict(snapshot=crop, time=time.strftime('%H:%M:%S'), scan_id=None,
                    mode='multi-chip' if multi else 'live' if live else 'scan')
        if multi:
            return self.scan_multi(crop, scan_frame, scan_frame_id, shot)
        if not verification:
            self.verification_request = None
        self.request_live = live
        self.performance['full_scan_requests'] = self.performance.get('full_scan_requests', 0)+1
        self.scan_serial += 1
        self.active_scan_id = shot['scan_id'] = self.scan_serial
        self.pending_snapshot = shot if live else None
        if not live:
            self.show_scan_snapshot(shot)
        if live:
            self.tracking_worker.begin(self.epoch, self.active_scan_id, scan_frame_id, scan_frame, self.roi)
        if verification:
            self.verification_request = (self.active_scan_id, scan_frame_id, self.epoch)
        else:
            self.overlay = 'Live: reading…' if live else 'Reading frozen snapshot…'
        self.busy = True
        if not live:
            self.clear_results('Scanning snapshot…')
        body_mode = self.auto_body.get()
        if body_mode and self.detector_body.get():
            # Trained detector on the whole frame; its body is used when it lies
            # fully inside the selection (else the full selection is scanned).
            body_mode = DetectorBody(scan_frame, tuple(self.roi), self.detector_model_path, scan_frame_id,
                                     self.detections_state)
        observing = bool(live and not verification and self.observation_mode)
        self.tasks.put(ScanRequest(
            epoch=self.epoch, crop=crop, mode='Live' if live else self.SNAPSHOT_MODE,
            known=tuple(self.cache), catalog=self.catalog,
            scan_id=self.active_scan_id, auto_body=body_mode,
            observation_live=observing, verification=verification,
            retry_attempt=self.rescan_policy.attempts if live else 0,
            preprocessing=None if live else self.snapshot_preprocessing))
        if observing and observation is None:
            policy = self.observation_policy
            policy.observe(scan_frame, scan_frame_id, time.monotonic(), roi=self.roi)
            if policy.last_sample is not None:
                policy.record_acquisition(policy.last_sample)
        self.ocr_state.set('Scanning…')
        return True

    SNAPSHOT_MODE = 'Original'   # preferred treatment of a frozen snapshot

    def clear_results(self, detail):
        """Forget the readings of the previous scan before a new one starts."""
        self.manual_choice = None
        self.rows = []
        self.diagnostics = {}
        self.scan_result = None
        self.filtered_rows = []
        self.lines.delete(0, 'end')
        self.marking.set('')
        self.detail.set(detail)

    def show_scan_snapshot(self, shot):
        """Show a scan's snapshot in the sidebar; it now belongs to the displayed readings."""
        self.snapshot, self.snapshot_time = shot['snapshot'], shot['time']
        self.displayed_scan = dict(scan_id=shot['scan_id'], mode=shot['mode'])
        self.preview_snapshot()

    def scan_multi(self, crop, frame, frame_id, shot=None):
        """Experimental (0.8.3.7): find every chip in the selection and read each
        one with the normal single-chip pipeline and the current settings."""
        self.scan_serial += 1
        self.active_scan_id = self.scan_serial
        self.request_live = False
        self.pending_snapshot = None
        if shot is not None:
            shot['scan_id'] = self.active_scan_id
            self.show_scan_snapshot(shot)
        self.multi_state = None
        self.clear_results('Scanning chips…')
        h, w = frame.shape[:2]
        offset = (max(0, int(self.roi[0]*w)), max(0, int(self.roi[1]*h)))
        detector = None
        if self.auto_body.get() and self.detector_body.get():
            detector = self.detector_model_path or ''
        self.performance['multi_chip_scans'] = self.performance.get('multi_chip_scans', 0)+1
        self.busy = True
        self.tasks.put(MultiRequest(epoch=self.epoch, scan_id=self.active_scan_id,
                                    crop=crop, frame=frame, frame_id=frame_id, offset=offset,
                                    known=tuple(self.cache), catalog=self.catalog,
                                    auto_body=bool(self.auto_body.get()), detector=detector,
                                    mode=self.SNAPSHOT_MODE, preprocessing=self.snapshot_preprocessing))
        self.overlay = 'Multi-chip: finding chips…'
        self.ocr_state.set('Multi-chip scan…')
        return True

    # --------------------------------------------------------------- OCR thread
    def ocr_worker(self):
        # Load models in the existing background worker before the first request.
        try:
            engine = OCR()
            # First inference initialises ONNX kernels; do it before the first scan.
            if callable(getattr(type(engine), 'warm_up', None)):
                engine.warm_up()
        except Exception:
            logging.exception('OCR preload failed; retrying on first scan')
            engine = None
        self.ocr_ready.set()
        while True:
            task = self.tasks.get()
            if task is None:
                return
            try:
                task = as_request(task)
            except (TypeError, ValueError):
                logging.exception('Ignored malformed OCR request')
                continue
            if isinstance(task, MultiRequest):
                outcome, engine = self.read_multi(engine, task)
            elif isinstance(task, RefineRequest):
                outcome, engine = self.read_refinement(engine, task)
            else:
                outcome, engine = self.read_scan(engine, task)
            self.results.put(outcome)

    def read_refinement(self, engine, task):
        """Live voting: re-read one tracked line in a newer frame (no detection)."""
        if task.epoch != self.epoch:
            return RefineResult.of(task), engine
        try:
            if engine is None:
                engine = OCR()
            reading = engine.read_line(task.frame, task.box, both_directions=not task.observation_live)
            return RefineResult.of(task, reading=reading), engine
        except Exception as exc:
            logging.exception('Line re-read failed')
            return RefineResult.of(task, error=str(exc)), engine

    def read_scan(self, engine, task):
        """One single-chip ScanRequest -> (ScanResultMsg, engine)."""
        epoch, mode, scan_id = task.epoch, task.mode, task.scan_id
        if epoch != self.epoch:
            return ScanResultMsg(epoch, [], 0., None, {}, scan_id), engine
        try:
            if engine is None:
                engine = OCR()

            def cancelled():
                if epoch != self.epoch or self.closing.is_set():
                    return True
                state = self.tracking_worker.snapshot() if mode == 'Live' else None
                return bool(state and state.get('acquiring') == scan_id and state.get('acquisition_lost'))
            engine.cancelled = cancelled
            engine.preprocessing = task.preprocessing if not task.live else None
            engine.verification = task.verification
            engine.acquisition_only = bool(task.observation_live and task.live and not task.verification)
            engine.fast = True if engine.acquisition_only else self.fast_mode
            engine.targeted_original = self.targeted_original_mode
            engine.live_primary_original = not bool(task.retry_attempt % 2)
            detection = None
            if isinstance(task.auto_body, DetectorBody):
                detection = self.detector_body_for(*task.auto_body.arguments())
            rows, elapsed = read_with_body(engine, task.crop, enabled=bool(task.auto_body), detection=detection,
                                           preferred=mode, known=task.known, live=task.live,
                                           catalog=task.catalog)
            return ScanResultMsg(epoch, rows, elapsed, None, engine.last_diagnostics, scan_id), engine
        except ScanCancelled:
            return ScanResultMsg(epoch, [], 0., None, {'cancelled': True}, scan_id), engine
        except Exception as exc:
            logging.exception('OCR failed')
            return ScanResultMsg(epoch, [], 0, str(exc), {}, scan_id), engine

    def read_multi(self, engine, task):
        """One MultiRequest -> (MultiResult, engine)."""
        task = as_request(task)
        epoch = task.epoch
        result = MultiResult(epoch=epoch, scan_id=task.scan_id, frame=task.frame,
                             frame_id=task.frame_id, offset=task.offset)
        if epoch != self.epoch:
            result.cancelled = True
            return result, engine

        def cancelled():
            return epoch != self.epoch or self.closing.is_set()
        try:
            if engine is None:
                engine = OCR()
            engine.cancelled = cancelled
            engine.verification = False
            engine.preprocessing = task.preprocessing
            engine.acquisition_only = False
            engine.fast = self.fast_mode
            engine.targeted_original = self.targeted_original_mode
            engine.live_primary_original = False
            detections, note = None, 'Chip detector not used (Body from chip detector off)'
            if task.detector is not None:
                detections, note = self.multi_detections(task.frame, task.detector)
            chips, summary = multi_chip.read_chips(
                engine, task.crop, read=read_with_body, auto_body=task.auto_body,
                detections=detections, offset=task.offset, cancelled=cancelled,
                preferred=task.mode, known=task.known, live=False, catalog=task.catalog)
            multi_chip.to_frame(chips, task.offset)
            summary.update(detector=note, runtime=getattr(engine, 'runtime', {}))
            result.chips, result.summary = chips, summary
        except ScanCancelled:
            result.cancelled = True
        except Exception as exc:
            logging.exception('Multi-chip scan failed')
            result.error = str(exc)
        return result, engine

    def multi_detections(self, frame, model_path):
        """Whole-frame detector bodies, or (None, reason)."""
        detector, error = ic_detector.shared_detector(model_path or None)
        if detector is None:
            return None, 'Chip detector unavailable: ' + (error or 'no model')
        try:
            found, _ = detector.detect_cached(frame, native_preprocessing=self.detector_alignment_mode)
            return found, f'{len(found)} detector bodies in the frame'
        except Exception as exc:
            logging.exception('Multi-chip detector failed')
            return None, 'Chip detector error: ' + str(exc)

    def detector_body_for(self, frame, roi, model_path=None, frame_id=None, cached=None):
        """Body outline from the trained detector, or the geometric locator's
        result when the model is unavailable."""
        if (cached is not None and frame_id is not None and
                cached.get('frame_id') == frame_id and not cached.get('error') and
                cached.get('shape') == frame.shape[:2] and
                cached.get('model_path') == model_path and
                cached.get('native_preprocessing', True) == self.detector_alignment_mode):
            return ic_detector.body_for_selection(cached['detections'], roi, frame.shape)
        detector, error = ic_detector.shared_detector(model_path)
        if detector is None:
            logging.warning('Detector body crop unavailable: %s', error)
            return geometric_fallback(crop_roi(frame, roi), 'Trained model unavailable: ' + str(error or 'no model'))
        started = time.perf_counter()
        try:
            found, timing = detector.detect_cached(frame, native_preprocessing=self.detector_alignment_mode)
        except Exception as exc:
            logging.exception('Detector body crop failed')
            return geometric_fallback(crop_roi(frame, roi), 'Trained model failed: ' + str(exc))
        result = ic_detector.body_for_selection(found, roi, frame.shape, started)
        result.update(cache_hit=timing['cache_hit'], cache_age_ms=timing['cache_age_ms'])
        return result

    # ------------------------------------------------------------ Tk thread: results
    def accept_results(self):
        try:
            result = as_result(self.results.get_nowait())
        except queue.Empty:
            return
        self.busy = False
        if isinstance(result, MultiResult):
            self.accept_multi(result)
        elif isinstance(result, RefineResult):
            self.accept_refinement(result)
        else:
            self.accept_scan(result)

    def accept_scan(self, result):
        epoch, rows, elapsed, error = result.epoch, result.rows, result.elapsed, result.error
        diagnostics, scan_id = result.diagnostics, result.scan_id
        self.next_live_scan = time.monotonic() + tuning('timing.post_scan_seconds')
        if epoch != self.epoch or scan_id != self.active_scan_id:
            self.ocr_state.set('Scene changed; waiting for a fresh scan.')
            return
        if self.verification_request and self.verification_request[0] == scan_id:
            if not self.accept_verification(result):
                return
        if diagnostics.get('cancelled'):
            self.performance['cancelled_scans'] = self.performance.get('cancelled_scans', 0)+1
            self.tracking_worker.resolve(epoch, scan_id, None)
            self.tracking_pending = None
            self.scene_guard.reset()
            self.next_live_scan = time.monotonic()+tuning('timing.cancel_retry_seconds')
            self.overlay = 'Live: waiting for a stable view…'
            return
        if error:
            if self.request_live:
                self.live.set(False)
                self.scene_guard.reset()
                self.invalidate()
                self.overlay = 'Live paused — OCR error: ' + error
            self.diagnostics = dict(diagnostics, error=error)
            self.ocr_state.set('OCR error: '+error)
            self.detail.set('OCR failed; see Diagnostics.')
            return
        pending = self.pending_snapshot
        if pending is not None and pending['scan_id'] == scan_id:
            # This Live result replaces the displayed one: so do its snapshot and preview.
            self.pending_snapshot = None
            self.show_scan_snapshot(pending)
        self.diagnostics = diagnostics
        if self.observation_mode and self.request_live:
            diagnostics['live_observation'] = self.observation_policy.snapshot()
        self.record_ocr_timings(elapsed, diagnostics)
        self.show_body_outline()
        self.show_runtime(diagnostics.get('runtime', {}), elapsed)
        self.filtered_rows = rows
        self.scan_result = diagnostics.get('scan_result')
        if self.scan_result is None:
            self.scan_result = build_scan_result(rows, diagnostics.get('all_candidates', rows), self.catalog)
        selected = self.scan_result.get('selected')
        if self.diagram_panel is not None:
            self.diagram_panel.update(selected)
        if selected:
            logging.info('Accepted match: %s', json.dumps(
                {k: selected.get(k) for k in ('raw_text', 'resolved_partnumber', 'applied_rules')}))
        self.ocr_state.set(f'{len(rows)} markings • {elapsed:.2f}s')
        self.refresh_readings()
        candidates = self.scan_result['candidates']
        if self.session_history is not None:
            # Live mode records the frame-voted marking later (finish_vote), except an
            # exact database match, rather than every lot/date line.
            live_rows = [r for r in candidates[:1] if any(
                m.get('match_type') == 'exact' for m in r.get('database_matches', []))]
            self.session_history.add(live_rows if self.request_live else candidates,
                                     database_loaded=self.catalog is not None)
        if self.request_live and self.live.get():
            self.tracking_pending = scan_id
            target = selected or self.scan_result.get('provisional')
            self.tracking_worker.resolve(self.epoch, scan_id, target)
            self.overlay = 'Live: locating snapshot in video…'

    def accept_verification(self, result):
        """Bounded re-scan of a tracked target: True when its result replaces the
        current one, False when the existing result is retained."""
        epoch, rows, error, diagnostics = result.epoch, result.rows, result.error, result.diagnostics
        frame_id = self.verification_request[1]
        self.verification_request = None
        decision = diagnostics.get('scan_result')
        if decision is None:
            decision = build_scan_result(rows, diagnostics.get('all_candidates', rows), self.catalog)
        candidate = decision.get('selected')
        state = self.tracking_worker.snapshot()
        valid = bool(state and state.get('epoch') == epoch and state.get('inside')
                     and state.get('row') and not state.get('recovering')
                     and not state.get('acquisition_lost') and self.scan_verification.get()
                     and not self.manual_choice and not error and not diagnostics.get('cancelled'))
        accepted = valid and self.verification.accept(self.verification_incumbent(), candidate, frame_id)
        evidence = dict(attempt=self.verification.attempts, accepted=bool(accepted),
                        candidate=(candidate or {}).get('key'), error=error,
                        all_candidates=decision.get('all_candidates', []))
        self.diagnostics['scan_verification'] = evidence
        logging.info('Scan verification: %s', json.dumps(evidence, default=str))
        if not accepted:
            # Resolving None discards only the snapshot acquisition. The existing
            # tracker, vote, displayed rows and diagram remain untouched.
            self.tracking_worker.resolve(epoch, result.scan_id, None)
            self.ocr_state.set('Scan verification: existing result retained')
            return False
        diagnostics['scan_verification'] = evidence
        self.manual_choice = None
        return True

    def record_ocr_timings(self, elapsed, diagnostics):
        self.performance['ocr_total_ms'] = elapsed*1000
        passes = diagnostics.get('timings', {}).get('ocr_passes', [])
        for name in ('detection_ms', 'recognition_ms'):
            if any(name in p for p in passes):
                self.performance['ocr_'+name] = sum(p.get(name, 0.) for p in passes)
        self.performance['ocr_pass_count'] = len(passes)
        self.performance['live_budget_limited'] = float(diagnostics.get('live_budget_limited', False))

    def show_runtime(self, runtime, elapsed):
        """Footer processor/time and the Tools tab's OCR processor line."""
        footer, label = runtime_text(runtime or {}, elapsed)
        self.footer_state.set(footer)
        if label:
            self.runtime_state.set(label)

    def accept_multi(self, result):
        result = as_result(result, default='multi')
        if result.epoch != self.epoch or result.scan_id != self.active_scan_id:
            self.ocr_state.set('Scene changed; waiting for a fresh scan.')
            return
        if result.cancelled:
            self.overlay = 'Multi-chip scan cancelled — scan again'
            self.ocr_state.set('Multi-chip scan cancelled')
            return
        if result.error:
            self.overlay = 'Multi-chip scan failed — ' + result.error
            self.diagnostics = {'error': result.error}
            self.ocr_state.set('OCR error: '+result.error)
            self.detail.set('OCR failed; see Diagnostics.')
            return
        chips, summary = result.chips, result.summary
        self.multi_state = dict(epoch=self.epoch, scan_id=result.scan_id, frame=result.frame,
                                frame_id=result.frame_id, offset=result.offset, chips=chips, summary=summary)
        if self.diagram_panel is not None:
            self.diagram_panel.update(None, multi=True)
        self.diagnostics = dict(multi_chip=summary, multi_chips=chips, runtime=summary.get('runtime', {}))
        elapsed = summary.get('total_ms', 0.)/1000
        self.performance['multi_chip_ms'] = summary.get('total_ms', 0.)
        self.performance['multi_chip_discovery_ms'] = summary.get('discovery_ms', 0.)
        self.performance['multi_chip_count'] = len(chips)
        self.show_runtime(summary.get('runtime'), elapsed)
        picked = sum(1 for chip in chips if chip.get('selected') is not None)
        self.ocr_state.set(f'{len(chips)} chips, {picked} automatic picks • {elapsed:.2f}s' +
                           (f" • {summary['skipped']} more not read (limit {multi_chip.MAX_CHIPS})"
                            if summary.get('skipped') else ''))
        self.refresh_readings()
        if self.session_history is not None:
            self.session_history.add([chip['selected'] for chip in chips if chip.get('selected')],
                                     database_loaded=self.catalog is not None)
        self.show_multi_outline()
