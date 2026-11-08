"""UI tick loop, background-result polling, deferred dialogs and shutdown."""
import logging
import queue
import threading
import time
from tkinter import messagebox

import click_log
from app_helpers import set_if_changed

TICK_MS = 33
STALE_FRAME_SECONDS = 2.


class LifecycleMixin:
    SHUTDOWN_SECONDS = 5.0   # total budget for joining workers on exit

    # ------------------------------------------------------------------ tick
    def tick(self):
        """UI loop (~30 Hz). 0.8.4.3: an exception in one tick is logged (rate
        limited) and shown in the status line; the loop always reschedules, so
        one bad frame or result no longer freezes the video for the session."""
        if self.closing.is_set():
            return
        now = time.monotonic()
        try:
            self.tick_once(now)
        except Exception as exc:
            self.report_tick_error(exc, now)
        finally:
            if not self.closing.is_set():
                tick_ms = (time.monotonic()-now)*1000
                try:
                    self.performance['ui_tick_ms'] = tick_ms
                finally:
                    self.root.after(max(1, int(TICK_MS-tick_ms)), self.tick)

    def report_tick_error(self, exc, now=None):
        if self.tick_errors.report(exc, now):
            try:
                self.ocr_state.set(f'Display error: {type(exc).__name__}: {exc} — see ICOCR.log'[:200])
            except Exception:
                logging.exception('Could not show the UI error')
        try:
            self.performance['ui_tick_errors'] = self.performance.get('ui_tick_errors', 0) + 1
        except Exception:
            pass

    def tick_once(self, now):
        if self.capture and not self.capture.stop_event.is_set():
            self.accept_frame(now)
        self.accept_devices()
        self.accept_database()
        self.update_sleep(now)
        self.update_live(now)
        self.update_detections()
        self.accept_results()
        self.accept_documentation()
        self.accept_click_errors()
        self.update_overlay_motion()
        self.draw()

    def accept_frame(self, now):
        frame, seq, timestamp, status = self.capture.snapshot()
        set_if_changed(self.state, status)
        if frame is not None and now-timestamp < STALE_FRAME_SECONDS:
            if seq != self.last_seq:
                self.frame = frame
                self.last_seq = seq
                self.frame_id += 1
        elif self.frame is not None:
            self.frame = None
            self.invalidate('Live video unavailable')
            self.state.set('Live video unavailable — frozen snapshot remains available')
            self.clear_canvas()
        if frame is None and not self.capture.is_alive():
            # The capture thread ended with an error; its status says why.
            self.overlay = 'Capture failed — choose another device/backend and press Start'

    # --------------------------------------------------------------- dialogs
    def show_dialog(self, kind, title, message, immediate=False):
        """Message box raised from the tick loop (0.8.4.8).

        Opening a modal dialog inside tick() kept the next tick from being
        scheduled, so video, Live tracking and OCR results stopped until the
        technician pressed OK. The dialog now opens from an idle callback after
        the tick has rescheduled itself; identical dialogs that are already
        waiting or open are not stacked.
        """
        key = (kind, title, message)
        if immediate:
            getattr(messagebox, kind)(title, message, parent=self.root)
            return
        if key in self.pending_dialogs:
            return
        self.pending_dialogs.append(key)

        def show():
            try:
                getattr(messagebox, kind)(title, message, parent=self.root)
            finally:
                if key in self.pending_dialogs:
                    self.pending_dialogs.remove(key)
        self.root.after_idle(show)

    # ------------------------------------------------- background notifications
    def accept_documentation(self, immediate=False):
        errors = []
        while True:
            try:
                kind, path, error = self.documentation.events.get_nowait()
            except queue.Empty:
                break
            refused = bool(error) and 'queue full' in error.lower()
            if kind == 'confirm' and not refused and self.confirm_pending:
                # One event per accepted confirmation, in submission order (0.8.8).
                key = self.confirm_pending.popleft()
                if error:
                    self.confirmed.discard(key)   # not logged: a new click retries
            if error and kind == 'capture' and refused:
                # 0.8.3.5: rapid Space presses — report in the status bar, no dialog.
                self.ocr_state.set('Capture skipped: still saving the previous images')
            elif error and kind == 'confirm':
                errors.append(error)
                self.ocr_state.set('Not logged: '+error+' — click the reading again to retry')
                self.archive_state.set('Confirmed reading not saved: '+error)
            elif error:
                errors.append(error)
                self.ocr_state.set('Save failed: '+error)
                self.archive_state.set('Save failed: '+error)
            elif kind == 'capture':
                self.ocr_state.set('Saved '+path.name)
            elif kind == 'confirm':
                self.archive_state.set('Saved '+path.name+' and its row in confirmed.csv')
                self.ocr_state.set('Logged '+path.name)
        if errors:
            self.show_dialog('showerror', 'Documentation save failed', '\n'.join(dict.fromkeys(errors)),
                             immediate=immediate)

    def accept_click_errors(self):
        """Click-history rows are written in the background (0.8.4.3)."""
        errors = click_log.take_errors()
        if not errors:
            return
        messages = list(dict.fromkeys(message for _, _, message in errors))
        self.ocr_state.set('Click was not logged: ' + messages[-1])
        self.show_dialog('showerror', 'Click was not logged',
                         'Could not write the click history. ' + '\n'.join(messages))

    # -------------------------------------------------------------- shutdown
    def close(self):
        if self.closing.is_set():
            return
        try:
            self.save_settings()
        except Exception:   # never keep the window open because settings failed
            logging.exception('Settings not saved on close')
        self.closing.set()
        self.close_started = time.monotonic()
        try:
            self.stop()
        except Exception:
            logging.exception('Stopping capture on close failed')

        # Joining workers must never block the Tk event loop.
        def shutdown():
            try:
                self.shutdown_workers(time.monotonic() + self.SHUTDOWN_SECONDS)
            except Exception:
                logging.exception('Shutdown of background workers failed')
            finally:
                self.shutdown_done.set()
        threading.Thread(target=shutdown, name='shutdown', daemon=True).start()
        self.root.after(50, self.finish_close)

    def shutdown_workers(self, deadline):
        """Stop and join every worker within one time budget (0.8.4.3).

        Workers still running at the deadline are logged and abandoned (all are
        daemon threads); the window closes anyway.
        """
        def left():
            return max(0., deadline - time.monotonic())
        stragglers = []

        def bounded(name, function):
            thread = threading.Thread(target=function, name='close-'+name, daemon=True)
            thread.start()
            return name, thread
        # Workers independent of the OCR thread close in parallel with it.
        closers = [bounded('tracking', self.tracking_worker.close),
                   bounded('overlay', self.overlay_worker.close),
                   bounded('click log', lambda: click_log.flush(self.SHUTDOWN_SECONDS))]
        if self.detector_worker is not None:
            closers.append(bounded('detector', self.detector_worker.close))
        # Wake the OCR worker. A request still waiting in the mailbox would be
        # cancelled anyway (closing is set), so it is replaced by the stop marker.
        while True:
            try:
                self.tasks.put_nowait(None)
                break
            except queue.Full:
                try:
                    self.tasks.get_nowait()
                except queue.Empty:
                    pass
                if not left():
                    stragglers.append('ocr (stop request not delivered)')
                    break
                time.sleep(.01)
        if self.ocr_thread is not None:
            self.ocr_thread.join(left())
            if self.ocr_thread.is_alive():
                stragglers.append('ocr')
        # The capture thread releases the device in its finally block.
        capture = self.capture
        if isinstance(capture, threading.Thread) and capture.is_alive():
            capture.stop_event.set()
            capture.join(left())
            if capture.is_alive():
                stragglers.append('capture (device not released)')
        if self.documentation is not None:
            closers.append(bounded('documentation', self.documentation.close))
        for name, thread in closers:
            thread.join(left())
            if thread.is_alive():
                stragglers.append(name)
        if stragglers:
            logging.warning('Shutdown: still running after %.1f s, closing anyway: %s',
                            self.SHUTDOWN_SECONDS, ', '.join(stragglers))
        self.shutdown_stragglers = stragglers
        return stragglers

    def finish_close(self):
        if self.close_started is None:
            self.close_started = time.monotonic()
        if not self.shutdown_done.is_set():
            # The shutdown thread sets shutdown_done within its budget; this
            # limit only guards against a shutdown thread that never returns.
            if time.monotonic() - self.close_started < self.SHUTDOWN_SECONDS + 2.:
                self.root.after(50, self.finish_close)
                return
            logging.warning('Shutdown did not finish; closing the window anyway')
        try:
            self.accept_documentation(immediate=True)
        except Exception:
            logging.exception('Final status update failed')
        finally:
            self.root.destroy()
