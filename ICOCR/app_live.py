"""Live recognition: tracking, frame voting, verification and overlay motion."""
import queue
import time

import multi_chip
from app_helpers import roi_view, set_if_changed
from component_catalog import annotate
from live_observation import ObservedVote
from overlay_motion import move_detection, move_points, move_row
from reading_vote import ReadingVote
from scan_messages import RefineRequest, as_result
from scan_verification import exact as verification_exact

MIN_CROP = 12                # pixels; smaller selections are not scene-checked
TRACKING_HOLD_SECONDS = .5   # tracked geometry stays drawable this long
DETECTION_HOLD_SECONDS = .75
PROJECTION_MAX_AGE = .18     # overlay-worker transforms older than this are not used


class LiveMixin:
    def request_refinement(self, state, observation=None):
        """Re-read only the tracked line in the newest tracked frame (no detection)."""
        vote = self.vote
        if vote is None or state['frame'] is None or state['frame_id'] == vote.last_frame_id:
            return False
        if observation is not None:
            state = dict(state, frame=observation.frame, frame_id=observation.frame_id,
                         row=dict(state['row'], box=observation.box))
        try:
            self.tasks.put_nowait(RefineRequest(epoch=self.epoch, vote=vote.serial,
                frame_id=state['frame_id'], frame=state['frame'], box=state['row']['box'],
                observation_live=bool(self.observation_mode)))
        except queue.Full:
            return False
        vote.last_frame_id = state['frame_id']
        self.busy = True
        return True

    def accept_refinement(self, result):
        result = as_result(result, default='refine')
        vote = self.vote
        if (vote is None or result.epoch != self.epoch or result.vote != vote.serial
                or vote.done()):
            return
        if result.error:
            self.ocr_state.set('Line re-read failed: '+result.error)
            vote.add(None, result.frame_id)
        else:
            vote.add(result.reading, result.frame_id)
        if result.reading and result.reading.get('milliseconds') is not None:
            self.performance['line_read_ms'] = result.reading['milliseconds']
        self.update_vote_row()
        self.overlay = ('Live: '+vote.view['text']+' — '+vote.summary())
        if vote.done():
            self.finish_vote()

    def update_vote_row(self):
        """Annotate the voted spelling with the database (evidence, not proof)."""
        vote = self.vote
        outcome = vote.result()
        if getattr(vote, 'view', None) is None or vote.view['key'] != outcome['key']:
            base = dict(vote.target, key=outcome['key'], text=outcome['key'], raw_text=outcome['key'],
                        observed_markings=[outcome['key']], conflicts=[])
            rows = annotate([base], self.catalog)
            vote.view = next((r for r in rows if r['key'] == outcome['key']), rows[0])
        vote.view = dict(vote.view, vote_summary=vote.summary(),
                         vote_confirmed=outcome['confirmed'])

    def finish_vote(self):
        vote = self.vote
        if vote.reported:
            return
        vote.reported = True
        outcome = vote.result()
        prototype = self.observation_mode
        if prototype:
            self.observation_policy.stable = outcome['confirmed']
            self.observation_policy.reason = ('Stable marking; tracking only' if outcome['confirmed']
                                              else 'Uncertain marking; waiting for a better view')
            self.diagnostics['live_observation'] = self.observation_policy.snapshot()
        if outcome['confirmed'] and (prototype or not vote.target.get('provisional') or
                                      vote.view.get('selected_database_match')):
            # Agreement stops further full rescans of this unchanged target.
            self.rescan_policy.confirmed = True
        if outcome['confirmed'] and self.diagram_panel is not None:
            self.diagram_panel.update(vote.view)
        if self.session_history is not None:
            self.session_history.add([vote.view], database_loaded=self.catalog is not None)

    def start_vote(self, row):
        self.vote_serial += 1
        prototype = self.observation_mode
        self.vote = ObservedVote(row) if prototype else ReadingVote(row)
        if prototype:
            self.observation_policy.start_track()
        if not self.verification.armed:
            self.verification.reset(time.monotonic())
            self.verification.armed = True
        self.vote.serial = self.vote_serial
        self.vote.view = None
        self.update_vote_row()

    def accept_tracking(self):
        state = self.tracking_worker.snapshot()
        if (state is None or state['epoch'] != self.epoch or
                state['version'] <= self.last_tracking_version):
            return
        self.last_tracking_version = state['version']
        previous = self.tracking_state
        self.tracking_state = state
        self.performance['tracking_ms'] = state['milliseconds']
        if state.get('recovery_count',0) != self.performance.get('recovery_count',0):
            self.performance['recovery_ms'] = state.get('recovery_ms',0.)
        self.performance['recovery_count'] = state.get('recovery_count',0)
        if state.get('recovery_search_ms',0):
            self.performance['recovery_search_ms'] = state['recovery_search_ms']
        if (self.tracking_pending is not None and state['resolved_request'] == self.tracking_pending
                and not state.get('recovering')):
            self.tracking_pending = None
            selected = state['row'] if state['resolution'] in ('tracking', 'held', 'recovered') else None
            self.rescan_policy.record(selected, time.monotonic())
            if selected is not None:
                self.start_vote(selected)
                provisional = not selected.get('selected_database_match')
                self.overlay = ('Live: checking reading across frames…' if provisional
                                else 'Live: tracking IC' if state['tracked'] else 'Live: label held')
            else:
                self.overlay = 'Live: no confirmed target — checking again'
            if (not self.observation_mode and not self.rescan_policy.confirmed
                    and self.rescan_policy.attempts > self.rescan_policy.MAX_RETRIES):
                self.overlay = f'Live: unresolved — retrying every {self.rescan_policy.SLOW_DELAY:g} seconds'
        elif state.get('recovering'):
            self.overlay = 'Live: reacquiring IC…'
        elif previous and previous.get('recovering') and state['row'] is not None:
            self.overlay = 'Live: tracking IC'
        elif previous and (previous['row'] is not None or previous.get('recovering')) and state['row'] is None:
            self.vote = None
            self.manual_choice = None
            self.verification.reset(time.monotonic())
            self.rescan_policy.reset()
            self.scene_guard.reset()
            self.observation_policy.reset()
            self.overlay = 'Live: tracking lost — acquiring again…'
        if state['error']:
            self.overlay = 'Live: tracking unavailable — ' + state['error']

    def verification_incumbent(self):
        state = self.tracking_state or {}
        vote = self.vote
        rows = [getattr(vote, 'view', None), state.get('row'),
                (self.scan_result or {}).get('selected')]
        return next((r for r in rows if verification_exact(r)),
                    next((r for r in rows if r and r.get('selected_database_match')),
                         next((r for r in rows if r), None)))

    def update_scan_verification(self, now):
        if not self.scan_verification.get() or self.catalog is None:
            return False
        state = self.tracking_state
        if (self.busy or self.tracking_pending is not None or self.manual_choice or
                not state or state.get('epoch') != self.epoch or not state.get('inside') or
                not state.get('row') or state.get('recovering')):
            return False
        if self.verification.ready(self.verification_incumbent(), now):
            if self.scan(live=True, verification=True):
                self.verification.started(now)
                return True
        return False

    def update_observation_live(self, now):
        policy = self.observation_policy
        state = self.tracking_state
        if state and state.get('recovering'):
            return
        inside = bool(state and state.get('row') is not None and state.get('inside'))
        if inside:
            self.tracking_in_roi = True
            if policy.observe(state['frame'], state['frame_id'], now, box=state['row']['box']):
                self.invalidate('Live: marking changed — acquiring again')
                return
            if self.busy or self.tracking_pending is not None:
                return
            vote = self.vote
            if vote is not None and not vote.done():
                sample = policy.refinement(now)
                if sample is not None and self.request_refinement(state, observation=sample):
                    policy.record_refinement(sample, now)
            else:
                policy.reason = ('Stable marking; tracking only' if policy.stable
                                 else 'Uncertain marking; waiting for a changed view')
        else:
            if self.tracking_in_roi:
                self.scene_guard.reset()
                policy.reset()
                self.vote = None
                self.tracking_in_roi = False
            crop = roi_view(self.frame, self.roi)   # read-only scene check: no copy per tick
            if min(crop.shape[:2]) < MIN_CROP:
                return
            if self.scene_guard.observe(crop, now):
                policy.reset()
            policy.observe(self.frame, self.frame_id, now, roi=self.roi)
            if self.busy or self.tracking_pending is not None:
                return
            sample = policy.acquisition(now) if self.scene_guard.ready(now) else None
            if sample is not None and self.scan(live=True, observation=sample):
                policy.record_acquisition(sample)
        self.performance['observation_full_scans'] = policy.full_scans
        self.performance['observation_line_reads'] = policy.line_reads
        self.diagnostics['live_observation'] = policy.snapshot()
        set_if_changed(self.ocr_state, 'Observation Live: '+policy.reason)

    def update_live(self, now):
        if self.idle_sleep.sleeping or not self.live.get() or self.drag or self.frame is None:
            return
        if self.multi_mode:
            return   # 0.8.3.7: multi-chip scans are manual (Enter / Scan)
        if self.submitted_frame_id != self.frame_id:
            self.submitted_frame_id = self.frame_id
            self.tracking_worker.submit(self.epoch, self.frame_id, self.frame, self.roi)
        self.accept_tracking()
        if self.update_scan_verification(now):
            return
        if self.observation_mode:
            self.update_observation_live(now)
            return
        if self.busy or self.tracking_pending is not None:
            return
        state = self.tracking_state
        if state and state.get('recovering'):
            return
        inside = bool(state and state['row'] is not None and state['inside'])
        if inside:
            self.tracking_in_roi = True
            vote = self.vote
            if vote is not None and not vote.done():
                self.request_refinement(state)
                return
            if (self.scan_verification.get() and self.catalog is not None
                    and self.verification.attempts < self.verification.MAX_SCANS
                    and not verification_exact(self.verification_incumbent())):
                return  # the bounded verification scheduler owns these retries
            if self.rescan_policy.ready(now):
                self.scan(live=True)
            return
        if self.tracking_in_roi:
            self.scene_guard.reset()
            self.rescan_policy.reset()
            self.tracking_in_roi = False
        crop = roi_view(self.frame, self.roi)
        if min(crop.shape[:2]) < MIN_CROP:
            return
        if self.scene_guard.observe(crop, now):
            self.rescan_policy.reset()
            self.overlay = 'Live: acquiring…'
        if self.scene_guard.ready(now) and self.rescan_policy.ready(now) and now >= self.next_live_scan:
            self.scan(live=True)

    def update_detections(self):
        worker = self.detector_worker
        show = self.show_detections.get()
        if worker is not None:
            worker.set_paused(bool(self.idle_sleep.sleeping or self.busy or not show))
        if self.idle_sleep.sleeping or worker is None or not show or self.frame is None:
            self.detections_state = None
            return
        if not self.busy and self.detector_submitted != self.frame_id:
            self.detector_submitted = self.frame_id
            worker.submit(self.frame_id, self.frame)
        state = worker.latest()
        if state is not None and state is not self.detections_state:
            self.detections_state = state
            self.performance['detector_ms'] = state['milliseconds']
            self.performance['body_cache_hit'] = float(state.get('cache_hit', False))
            self.performance['body_cache_age_ms'] = state.get('cache_age_ms', 0.)
            if state['error']:
                self.state.set('Chip detector: '+state['error'])

    def update_overlay_motion(self):
        if self.idle_sleep.sleeping or self.frame is None:
            return
        sources = []
        state = self.tracking_state
        if self.live.get() and state and state['epoch'] == self.epoch and state['row'] is not None:
            sources.append(state['frame'])
        state = self.detections_state
        if (state and not state.get('error') and state.get('detections') and
                self.show_detections.get()):
            sources.append(state.get('frame'))
        multi = self.multi_state
        if multi is not None and multi['epoch'] == self.epoch:
            sources.append(multi['frame'])
        self.overlay_worker.submit(self.epoch, self.frame, sources,
            payload={'tracking': self.tracking_state, 'detector': self.detections_state})
        result = self.overlay_worker.snapshot()
        if result is not None and result is not self._last_motion_result:
            self._last_motion_result = result
            self.performance['overlay_motion_ms'] = result['milliseconds']

    def projected_state(self, kind, latest):
        """Use geometry and transforms from the same publication, not mixed ticks."""
        result = self.overlay_worker.snapshot()
        if (result is None or result['epoch'] != self.epoch or
                time.monotonic()-result['submitted'] > PROJECTION_MAX_AGE):
            return latest
        state = (result.get('payload') or {}).get(kind)
        if state is None or latest is None:
            return latest
        if kind == 'tracking':
            if (not latest.get('row') or not state.get('row') or
                    latest.get('resolved_request') != state.get('resolved_request') or
                    latest['row'].get('key') != state['row'].get('key')):
                return latest
        elif (latest.get('error') or not latest.get('detections') or
              latest.get('model_path') != state.get('model_path') or
              latest.get('native_preprocessing') != state.get('native_preprocessing')):
            return latest
        return state

    def overlay_transform(self, source, current):
        return self.overlay_worker.matrix(self.epoch, source, current)

    def visible_detections(self, frame=None):
        state = self.projected_state('detector', self.detections_state)
        current = self.frame if frame is None else frame
        if (state is None or current is None or state['shape'] != current.shape[:2] or
                state.get('error') or
                state.get('model_path') != self.detector_model_path):
            return []
        source = state.get('frame')
        if source is current:
            return state['detections']
        if source is None:
            return state['detections'] if state['frame_id'] == self.frame_id and current is self.frame else []
        if time.monotonic() - state.get('completed', 0) > DETECTION_HOLD_SECONDS:
            return []
        matrix = self.overlay_transform(source, current)
        if matrix is None:
            return []
        return [move_detection(found, matrix) for found in state['detections']]

    def visible_chips(self, frame):
        """Multi-chip results projected onto the displayed frame, or [] when the
        view moved too far to place them (scan again)."""
        state = self.multi_state
        if state is None or state['epoch'] != self.epoch or frame is None:
            return []
        source = state['frame']
        if source is frame:
            matrix = None
        else:
            if source.shape != frame.shape:
                return []
            matrix = self.overlay_transform(source, frame)
            if matrix is None:
                if not self.chips_lost:
                    self.chips_lost = True
                    self.ocr_state.set('Multi-chip overlay hidden: the view moved — hold still or scan again')
                return []
        if self.chips_lost:
            self.chips_lost = False
            self.ocr_state.set(f"{len(state['chips'])} chips")
        placed = []
        for chip in state['chips']:
            row = multi_chip.reading_of(chip)
            box = row.get('box') if row is not None else None
            body = chip.get('body_box')
            if matrix is not None:
                box = move_points(box, matrix) if box is not None else None
                body = move_points(body, matrix) if body is not None else None
            placed.append(dict(chip=chip, box=box, body=body))
        return placed

    def display_state(self):
        """Keep current video and project recent worker geometry through motion."""
        state = self.projected_state('tracking', self.tracking_state)
        if (self.live.get() and state and state['epoch'] == self.epoch and state['row'] is not None and
                (state['frame'] is self.frame or time.monotonic()-state['completed'] < TRACKING_HOLD_SECONDS)):
            matrix = self.overlay_transform(state['frame'], self.frame)
            if matrix is not None:
                return self.frame, move_row(state['row'], matrix)
        return self.frame, None
