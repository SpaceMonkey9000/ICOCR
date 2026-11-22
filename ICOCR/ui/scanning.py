"""Manual and live scans, the recognition overlay and the recognised-markings list."""
import json
import webbrowser
from urllib.parse import quote_plus
import time
import cv2
import numpy as np
from PySide6.QtCore import QTimer
from package_pinouts import corrected_alias_label
from readings_list import build as build_readings, label as reading_label
from ui.workers import FullScanWorker


class ScanMixin:
    """Scanning and reading selection. Mixed into MainWindow."""

    # -- recognition overlay ---------------------------------------------------
    def _reset_idle_sleep(self):
        self._idle_reference = None
        self._idle_last_change = time.monotonic()
        self._ocr_sleeping = False

    def _reset_scene(self):
        """New camera or image: results of earlier scans no longer apply."""
        self._epoch += 1
        self._shown = self._pending = None
        self._live_matrices = {}
        self._frozen_matrix = None
        self._reset_idle_sleep()
        self.recognition_overlay.clear()
        if self.preview is not None:
            self.preview.keep(())

    def _tracked_epochs(self):
        return [state['epoch'] for state in (self._shown, self._pending) if state]

    def _draw_overlay(self):
        """Place the overlay for the frame that is on screen right now."""
        overlay = self.recognition_overlay
        if not self.overlay_enabled or not overlay or self._shown is None:
            overlay.draw(visible=False)
            return
        image = self._displayed()
        if image is self._shown['frame']:
            overlay.draw(None)                       # the scanned frame itself
        elif self.frozen is not None:
            overlay.draw(self._frozen_matrix, self._frozen_matrix is not None)
        else:
            matrix = self._live_matrices.get(self._shown['epoch'])
            overlay.draw(matrix, matrix is not None)

    # -- scanning --------------------------------------------------------------
    def scan(self, live=False):
        if self._closing:
            return
        if self.ocr_worker is not None and self.ocr_worker.isRunning():
            if not live:
                # Run the manual scan as soon as the current one ends; a live
                # scan is abandoned so the technician does not wait for it.
                self._queued_scan = True
                if self._pending and self._pending.get('live'):
                    self.ocr_worker.cancel()
                self.statusBar().showMessage('Scan queued')
            return
        image = self._displayed()
        if image is None:
            self.statusBar().showMessage('No frame to scan')
            return
        roi = tuple(self.view.roi)
        h, w = image.shape[:2]
        if min((roi[2]-roi[0])*w, (roi[3]-roi[1])*h) < 12:
            self.statusBar().showMessage('Select a larger region')
            return
        self._epoch += 1
        if not live:
            # Keep the full set of detected bodies selectable while the chosen
            # component is rescanned. Results are replaced atomically on completion.
            self.scan_btn.setEnabled(False)
            self.details.setPlainText('Scanning…')
            self._idle_last_change = time.monotonic()
            self._ocr_sleeping = False
        self._pending = dict(epoch=self._epoch, frame=image, roi=roi, live=live)
        if self.preview is not None:
            self.preview.keep(self._tracked_epochs())
            self.preview.track(self._epoch, image)
        settings = dict(body=self.body_enabled, fast=self.fast_enabled,
                        targeted=self.targeted_enabled, package=self.package_enabled,
                        package_model=str(self.effective_package_model()), body_model=self.body_model,
                        multi=self.multi_enabled,
                        body_only=self.body_only_enabled)
        self.ocr_worker = FullScanWorker(self._epoch, image, roi, self.catalog, settings, self)
        self.ocr_worker.scanned.connect(self.scan_done)
        self.ocr_worker.finished.connect(self._scan_worker_finished)
        self.ocr_worker.start()

    def _body_selected(self, roi):
        """Clicking a detected IC body replaces the current OCR selection.

        Hit-testing uses the displayed, motion-adjusted body outline. The
        returned ROI is in current source-frame coordinates, not preview pixels.
        """
        from qt_scan_region import expand_body_roi
        frame = self._displayed()
        if frame is None:
            return
        expanded = expand_body_roi(roi, (frame.shape[1], frame.shape[0]))
        self.view.set_roi(expanded)
        self.view.region_changed.emit(expanded)
        self.statusBar().showMessage('Component selected — expanded scan margin applied')
        self.scan(live=False)

    def _live_scan(self):
        if (self._closing or not self.live_recognition.isChecked() or self.capture is None
                or self.frozen is not None):
            # A frozen frame does not change: live OCR would only repeat itself
            # and overwrite results of a manual scan of that frame.
            self._reset_idle_sleep()
            return
        frame = self._displayed()
        if frame is None:
            return
        if self.sleep_enabled:
            # Sample a small grayscale image only once per live timer tick.
            # The preview never stops; sleep suppresses redundant OCR jobs.
            sample = cv2.cvtColor(cv2.resize(frame, (96, 54), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
            now = time.monotonic()
            if self._idle_reference is None:
                self._idle_reference = sample
                self._idle_last_change = now
            else:
                changed = float(cv2.absdiff(sample, self._idle_reference).mean()) > 5.0
                if changed:
                    self._idle_reference = sample
                    self._idle_last_change = now
                    if self._ocr_sleeping:
                        self.statusBar().showMessage('Live OCR resumed — scene changed')
                    self._ocr_sleeping = False
                elif now - self._idle_last_change >= self.sleep_seconds:
                    if not self._ocr_sleeping:
                        self.statusBar().showMessage('Live OCR sleeping — waiting for scene change')
                    self._ocr_sleeping = True
                    return
        else:
            self._reset_idle_sleep()
        self.scan(live=True)

    def scan_done(self, epoch, decision, diagnostics, elapsed, error):
        pending, self._pending = self._pending, None
        if self._closing or pending is None or pending['epoch'] != epoch:
            return      # the camera or image changed while this scan was running
        if error:
            if self.preview is not None:
                self.preview.keep(self._tracked_epochs())
            self.details.setPlainText(error)
            self.details_title.setChecked(True)
            self.statusBar().showMessage('Scan failed — see Diagnostics > Identification details')
            return
        self.decision, self.diagnostics = decision, diagnostics
        self.manual_chosen_row = None  # A new scan replaces the previous manual choice.
        # OCR boxes are relative to the scanned selection; the overlay places
        # them in the scanned frame using the region recorded for that scan.
        frame = pending['frame']
        chips = diagnostics.get('overlay_chips')
        if chips:
            rows = [chip['target'] for chip in chips
                    if chip.get('target') and chip['target'].get('box') is not None]
            bodies = [chip.get('body_box') for chip in chips]
        else:
            selected = (decision or {}).get('selected') or (decision or {}).get('provisional')
            rows = [selected] if selected and selected.get('box') is not None else []
            body = diagnostics.get('body_detection') or {}
            bodies = [body.get('box') or body.get('mask_polygon')]
        # The ONNX detector runs on the full source frame. Keep ALL fitted
        # four-corner package outlines, including when a single IC is selected,
        # translated into ROI-local coordinates for the overlay presenter.
        outlines = diagnostics.get('model_body_outlines') or []
        if outlines:
            ox = int(pending['roi'][0] * frame.shape[1])
            oy = int(pending['roi'][1] * frame.shape[0])
            bodies = [(np.asarray(p, dtype=float) - [ox, oy]).tolist()
                      for p in outlines]
        self.recognition_overlay.set_results(rows, bodies, pending['roi'],
                                             (frame.shape[1], frame.shape[0]),
                                             database_loaded=self.catalog is not None)
        self._shown = dict(epoch=epoch, frame=frame)
        if self.preview is not None:
            self.preview.keep([epoch])
        self._draw_overlay()

        previous_key = self._selected_key() if pending['live'] else None
        self._populate_readings()
        if decision:
            # Same policy as the session history: accepted candidates only.
            self.history_model.add(decision.get('candidates') or [], self.catalog is not None)
            self._refresh_history()
        self.diagnostic_text.setPlainText(json.dumps(
            self._diagnostic_summary(decision, diagnostics), indent=2, default=str))
        package = diagnostics.get('package_classification')
        try:
            from package_classifier import summary
            self.package_text = summary(package)
        except Exception:
            self.package_text = str(package or 'Package: unavailable')
        best = ((decision or {}).get('selected') or (decision or {}).get('provisional'))
        keys = [row.get('key') for row in self.display_rows]
        if previous_key in keys:
            self.results.setCurrentRow(keys.index(previous_key))   # keep the technician's row
        elif best and best.get('key') in keys:
            self.results.setCurrentRow(keys.index(best.get('key')))
        if diagnostics.get('detector_only') and not diagnostics.get('body_model_detections'):
            self.statusBar().showMessage('Body-only OCR: no detected IC bodies; OCR skipped'
                                         + (f" ({diagnostics['body_model_error']})" if diagnostics.get('body_model_error') else ''))
        else:
            self.statusBar().showMessage(
                f'Scan {elapsed:.2f}s | {len(self.display_rows)} readings | {self.package_text}')

    def _scan_worker_finished(self):
        worker = self.sender()
        if worker is self.ocr_worker:
            self.ocr_worker = None
        if worker is not None:
            worker.deleteLater()     # each worker holds a full-resolution frame
        if not self._closing:
            self.scan_btn.setEnabled(True)
            if self._queued_scan:
                self._queued_scan = False
                QTimer.singleShot(0, lambda: self.scan(live=False))
        self._finish_close_if_ready()

    def _diagnostic_summary(self, decision, diagnostics):
        # Full OCR structures are large and not JSON-serialisable; show the
        # selection evidence only.
        selected = (decision or {}).get('selected') or {}
        return dict(selected=selected.get('key'),
                    selected_part=(selected.get('selected_database_match') or {}).get('part'),
                    selection_reason=selected.get('selection_reason'),
                    candidates=[dict(key=r.get('key'), score=r.get('score'),
                                     reason=r.get('selection_reason'),
                                     exclusion=r.get('rejection_reason'))
                                for r in (decision or {}).get('all_candidates', [])],
                    package=diagnostics.get('package_classification'),
                    configuration=(decision or {}).get('configuration'))

    # -- readings --------------------------------------------------------------
    def _selected_key(self):
        i = self.results.currentRow()
        return self.display_rows[i].get('key') if 0 <= i < len(self.display_rows) else None

    def _populate_readings(self, *_):
        if self.decision is None:
            return
        self.results.blockSignals(True)
        self.results.clear()
        entries = build_readings(self.decision, self.diagnostics, show_all=self.show_all.isChecked(),
                                 chosen=self.manual_chosen_row)
        self.display_rows = [r for r, kind in entries]
        for row, kind in entries:
            self.results.addItem(reading_label(row, kind))
        self.results.blockSignals(False)
        self.datasheet_btn.setEnabled(False)
        if not self.display_rows:
            self.details.setPlainText('No eligible readings. Inspect recognition diagnostics or adjust selection.')
            self.pinout_title.setText('No component identified')
            self.reference_choices = []
            self.reference_select.blockSignals(True)
            self.reference_select.clear()
            self.reference_select.blockSignals(False)
            self._render_reference(-1)

    def _reading_chosen(self):
        i = self.results.currentRow()
        if not 0 <= i < len(self.display_rows):
            return
        row = self.display_rows[i]
        match = row.get('selected_database_match') or {}
        alias_details = []
        if row.get('corrected_alias_issue'):
            alias_details = [row['corrected_alias_issue']]
            alias_details += [f"{row.get('text') or row['key']} → {corrected_alias_label(candidate)}"
                              for candidate in row['corrected_alias_suggestions']]
        elif match.get('match_type') == 'corrected_alias':
            alias_details = [f"{row.get('text') or row['key']} → {corrected_alias_label(match)}"]
        self.details.setPlainText('\n'.join([
            'Marking: ' + str(row.get('key', '')),
            'OCR confidence: ' + str(row.get('score', '')),
            'ICDB part: ' + str(match.get('part', 'No confirmed DB match')),
            'Manufacturer: ' + str(match.get('manufacturer', '')),
            'Package: ' + str(match.get('package', '')),
            'Evidence: ' + str(row.get('status', '')),
            'Exclusion: ' + str(row.get('rejection_reason', '')),
            *(['Ambiguous marking alias. Double-click this reading to choose a device.']
              + [f"{part} · {maker or 'Manufacturer unspecified'}" for part, maker in
                 dict.fromkeys((m['part'], m.get('manufacturer')) for m in row['database_matches'])]
              if row.get('alias_ambiguous') else []),
            *alias_details,
        ]))
        self._pinout_for(row)
        self._update_datasheet(row)

    def _choose_reading(self, item):
        """Double-click confirms this reading and records it in History.

        This changes only the current UI selection and history, not the OCR
        ranking rules or the stored ICDB catalogue.
        """
        index = self.results.row(item)
        if not 0 <= index < len(self.display_rows):
            return
        row = self.display_rows[index]
        if row.get('alias_ambiguous'):
            from PySide6.QtWidgets import QInputDialog
            choices = {f"{m['part']} · {m.get('manufacturer') or 'Manufacturer unspecified'}": m
                       for m in row['database_matches']}
            selected, ok = QInputDialog.getItem(self, 'Choose alias target', 'Device', list(choices), 0, False)
            if not ok:
                return
            match = choices[selected]
            row = dict(row, selected_database_match=match, resolved_partnumber=match['part'],
                       rejection_reason='', provisional=False, alias_ambiguous=False,
                       function_summary=match.get('component_function', ''))
        self.manual_chosen_row = row
        self.history_model.add_selected(row, self.catalog is not None)
        self._refresh_history()
        self._populate_readings()  # Shows the chosen marker at the top.
        self.results.setCurrentRow(0)
        self.statusBar().showMessage(
            f"Selected marking {row.get('text') or row.get('key')} — added to History")

    def _search_reading(self, item):
        index = self.results.row(item)
        if not 0 <= index < len(self.display_rows):
            return
        row = self.display_rows[index]
        match = row.get('selected_database_match') or {}
        part = str(match.get('part') or row.get('key') or '').strip()
        if part:
            webbrowser.open('https://www.google.com/search?q=' + quote_plus(part + ' ic datasheet'))

    def _selected_part_number(self):
        index = self.results.currentRow()
        if not 0 <= index < len(self.display_rows):
            return ''
        row = self.display_rows[index]
        match = row.get('selected_database_match') or {}
        return str(match.get('part') or row.get('key') or '').strip()

    def _update_datasheet(self, row):
        match = row.get('selected_database_match') or {}
        part = str(match.get('part') or row.get('key') or '').strip()
        self.datasheet_btn.setEnabled(bool(part))
        self.datasheet_btn.setToolTip('Search: ' + part + ' ic datasheet' if part
                                      else 'Select a recognised marking first')

    def _search_selected_datasheet(self):
        part = self._selected_part_number()
        if part:
            webbrowser.open('https://www.google.com/search?q=' + quote_plus(part + ' ic datasheet'))
