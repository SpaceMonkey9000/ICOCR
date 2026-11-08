from config_loader import tuning
"""Fast acquisition retries followed by periodic recovery for unresolved targets."""


class RescanPolicy:
    MAX_RETRIES = tuning('timing.max_retries')
    SLOW_DELAY = tuning('timing.slow_delay')
    DELAYS = tuple(tuning(f'timing.retry_{i}_seconds') for i in (1,2,3))

    def __init__(self):
        self.reset()

    def reset(self):
        self.attempts = 0
        self.next_at = 0.0
        self.confirmed = False

    def record(self, selected, now):
        self.confirmed = bool(selected and selected.get('selected_database_match') and not selected.get('provisional'))
        self.attempts += 1
        delay = (self.SLOW_DELAY if self.attempts > self.MAX_RETRIES else
                 self.DELAYS[min(self.attempts-1, len(self.DELAYS)-1)])
        self.next_at = now + delay

    def ready(self, now):
        return not self.confirmed and now >= self.next_at

