"""Multi-frame agreement for one tracked text line (live refinement).

Each live frame re-reads only the tracked line (recognition, no detection).
Readings are counted per spelling; when spellings differ by isolated
characters, a per-character vote over equal-length readings can agree instead.
Agreement is evidence of a stable reading, not proof of a part identity.
"""
from config_loader import tuning
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from ocr_core import line_tokens


class ReadingVote:
    MIN_VOTES = 3      # agreeing frames needed to confirm
    MIN_SHARE = tuning('reading_vote.minimum_share')     # share of usable readings that must agree
    MAX_READS = 12     # stop re-reading this target after this many frames
    MIN_SCORE = tuning('reading_vote.minimum_score')    # recogniser score below this is a miss
    MIN_SIMILARITY = tuning('reading_vote.minimum_similarity')

    def __init__(self, row, seed=True):
        self.target = dict(row)
        self.base = row['key']
        self.alternatives = [k for k in row.get('conflicts') or [] if k != self.base]
        self.votes = []          # (key, score)
        self.reads = 0
        self.misses = 0
        self.last_frame_id = None
        self.milliseconds = []
        self.reported = False
        if seed:
            self.votes.append((self.base, float(row.get('score', 0))))

    def token(self, text):
        """The token of a line reading that corresponds to the tracked marking."""
        references = [self.base] + self.alternatives
        best, similarity = None, 0.
        for row in line_tokens(text, 0, 0, '', None):
            value = max(SequenceMatcher(None, row['key'], ref).ratio() for ref in references)
            if value > similarity:
                best, similarity = row['key'], value
        return best if similarity >= self.MIN_SIMILARITY else None

    def add(self, reading, frame_id=None):
        self.reads += 1
        self.last_frame_id = frame_id
        if reading and reading.get('milliseconds') is not None:
            self.milliseconds.append(reading['milliseconds'])
        # Preserve the tracked spelling when the opposite direction scores
        # slightly higher. Only one vote per frame; unrelated text is a miss.
        if reading and reading.get('alternatives'):
            plausible = [r for r in reading['alternatives']
                         if r.get('score', 0) >= self.MIN_SCORE and self.token(r['text'])]
            if plausible:
                reading = max(plausible, key=lambda r: r['score'])
        key = self.token(reading['text']) if reading and reading.get('score', 0) >= self.MIN_SCORE else None
        if key is None:
            self.misses += 1
            return None
        self.votes.append((key, float(reading['score'])))
        return key

    def tally(self):
        counts = Counter(key for key, _ in self.votes)
        return counts.most_common()

    def result(self):
        """Current leading reading and whether frames agree enough to confirm."""
        if not self.votes:
            return dict(key=self.base, count=0, total=0, share=0., confirmed=False, method='')
        total = len(self.votes)
        counts = self.tally()
        key, count = counts[0]
        # Ties: prefer the higher summed recogniser score.
        tied = [k for k, c in counts if c == count]
        if len(tied) > 1:
            weight = defaultdict(float)
            for k, s in self.votes:
                weight[k] += s
            key = max(tied, key=lambda k: weight[k])
        share = count / total
        if count >= self.MIN_VOTES and share >= self.MIN_SHARE:
            return dict(key=key, count=count, total=total, share=share, confirmed=True, method='string')
        consensus = self.character_consensus()
        if consensus:
            return consensus
        return dict(key=key, count=count, total=total, share=share, confirmed=False, method='')

    def character_consensus(self):
        """Per-position majority among equal-length readings (isolated misreads)."""
        lengths = Counter(len(k) for k, _ in self.votes)
        length, group_size = lengths.most_common(1)[0]
        group = [k for k, _ in self.votes if len(k) == length]
        if group_size < self.MIN_VOTES + 1 or group_size / len(self.votes) < self.MIN_SHARE:
            return None
        chars, weakest = [], 1.
        for i in range(length):
            char, n = Counter(k[i] for k in group).most_common(1)[0]
            chars.append(char)
            weakest = min(weakest, n / group_size)
        if weakest < self.MIN_SHARE:
            return None
        key = ''.join(chars)
        return dict(key=key, count=group_size, total=len(self.votes),
                    share=weakest, confirmed=True, method='character')

    def done(self):
        return self.result()['confirmed'] or self.reads >= self.MAX_READS

    def summary(self):
        result = self.result()
        if result['confirmed']:
            how = 'per-character vote' if result['method'] == 'character' else 'frames agree'
            return f"{result['count']}/{result['total']} {how}"
        if self.reads >= self.MAX_READS:
            return f"no agreement after {self.reads} reads"
        return f"checking {self.reads}/{self.MAX_READS}"
