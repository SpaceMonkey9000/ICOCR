"""Sleep scheduling on the Tk thread; active OCR is allowed to finish."""
import time
from app_helpers import set_if_changed


class SleepMixin:
    def sleep_timeout(self):
        try:
            value = int(self.sleep_seconds.get())
        except (TypeError, ValueError):
            value = 120
        return max(5, min(3600, value))

    def wake_for_action(self):
        if self.idle_sleep.touch(time.monotonic()):
            self.resume_from_sleep()

    def resume_from_sleep(self):
        self.invalidate('Awake — ready to scan')
        self.detections_state = None
        self.detector_submitted = -1
        self.next_live_scan = 0.
        self.ocr_state.set('Awake — waiting for a stable view')

    def change_sleep_settings(self):
        self.sleep_seconds.set(str(self.sleep_timeout()))
        self.wake_for_action()
        self.save_settings()

    def update_sleep(self, now):
        active_camera = (self.capture is not None and not self.capture.stop_event.is_set()
                         and self.frame is not None)
        transition = self.idle_sleep.observe(self.frame, self.frame_id, now,
            timeout=self.sleep_timeout(), enabled=bool(self.sleep_enabled.get() and active_camera),
            can_sleep=not self.busy and not self.drag)
        if transition == 'sleep':
            self.invalidate('Sleeping — waiting for movement', preserve_reference=True)
            self.detections_state = None
            self.detector_submitted = -1
            if self.detector_worker is not None:
                self.detector_worker.set_paused(True)
                self.detector_worker.discard_results()
        elif transition == 'wake':
            self.resume_from_sleep()
        if self.idle_sleep.sleeping:
            set_if_changed(self.ocr_state, 'Sleeping — waiting for movement')
