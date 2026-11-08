"""Bounded rolling samples, written/read only by the UI thread."""
from collections import defaultdict, deque
import math
import statistics


class Performance(dict):
    def __init__(self, capacity=240):
        super().__init__()
        self.samples = defaultdict(lambda: deque(maxlen=capacity))

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        if (key.endswith('_ms') or key == 'preview_fps') and math.isfinite(value):
            self.samples[key].append(float(value))

    def summaries(self):
        for key, samples in sorted(self.samples.items()):
            values = sorted(samples)
            yield key, len(values), statistics.median(values), values[math.ceil(.95*len(values))-1]
