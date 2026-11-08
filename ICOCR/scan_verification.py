"""Bounded independent rescans; failed checks never replace displayed evidence."""

def exact(row):
    match = (row or {}).get('selected_database_match') or {}
    return bool(match.get('match_type') in ('exact', 'verified_alias') and
                not row.get('database_ambiguous') and not row.get('provisional') and
                not row.get('conflicts') and not row.get('ocr_correction'))


class ScanVerification:
    DELAY = 1.2
    MAX_SCANS = 3

    def __init__(self):
        self.reset()

    def reset(self, now=0.):
        self.armed = False
        self.attempts = 0
        self.next_at = now + self.DELAY
        self.candidate = None
        self.count = 0
        self.frame_id = None

    def ready(self, row, now):
        return not exact(row) and self.attempts < self.MAX_SCANS and now >= self.next_at

    def started(self, now):
        self.attempts += 1
        self.next_at = now + self.DELAY

    def accept(self, incumbent, candidate, frame_id):
        if exact(incumbent) or not exact(candidate):
            self.candidate, self.count = None, 0
            return False
        match = candidate['selected_database_match']
        identity = (match['part'].upper(), match.get('package', ''))
        if frame_id == self.frame_id:
            return False
        self.frame_id = frame_id
        self.count = self.count + 1 if identity == self.candidate else 1
        self.candidate = identity
        return self.count >= 2
