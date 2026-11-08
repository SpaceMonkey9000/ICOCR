"""Typed messages between the Tk controller and the OCR worker (0.8.4.3).

Before 0.8.4.3 scan requests and results were positional tuples (and dicts for
line refinement and multi-chip scans) unpacked by position in three places.
These small dataclasses name every field. For older callers (tests, tools)
`as_request` / `as_result` still accept the legacy tuple and dict shapes, and
every message supports read-only mapping access (``msg['epoch']``,
``dict(msg)``).
"""
from dataclasses import dataclass, field, fields
from typing import Any, ClassVar, Optional


class _MappingAccess:
    """Read-only dict-style access kept for callers written against the old dicts."""
    kind: ClassVar[str] = ''

    def __getitem__(self, key):
        if key == 'kind':
            return self.kind
        if key in self._names():
            return getattr(self, key)
        raise KeyError(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def keys(self):
        return ['kind', *self._names()]

    def __contains__(self, key):
        return key in self.keys()

    @classmethod
    def _names(cls):
        return [f.name for f in fields(cls)]

    @classmethod
    def from_mapping(cls, values):
        names = set(cls._names())
        return cls(**{k: v for k, v in dict(values).items() if k in names})


@dataclass(frozen=True)
class DetectorBody(_MappingAccess):
    """Use the trained detector's body outline inside the selection."""
    kind: ClassVar[str] = 'detector'
    frame: Any
    roi: tuple
    model_path: Optional[str] = None
    frame_id: Optional[int] = None
    cached: Optional[dict] = None

    def __bool__(self):
        return True   # body cropping is enabled

    def arguments(self):
        return self.frame, self.roi, self.model_path, self.frame_id, self.cached


@dataclass
class ScanRequest(_MappingAccess):
    """One single-chip scan of a frozen crop (Enter/Scan or Live acquisition)."""
    kind: ClassVar[str] = 'scan'
    epoch: int
    crop: Any
    mode: str
    known: tuple
    catalog: Any
    scan_id: int
    auto_body: Any = False          # bool, or DetectorBody
    observation_live: bool = False
    retry_attempt: int = 0
    preprocessing: Optional[dict] = None
    verification: bool = False

    @property
    def live(self):
        return self.mode == 'Live'

    @classmethod
    def from_tuple(cls, task):
        # Legacy tuples still carry the archive flag removed in 0.8.4.8; it is ignored.
        epoch, crop, mode, known, catalog, _archive, scan_id, auto_body, *options = task
        if isinstance(auto_body, tuple) and auto_body and auto_body[0] == 'detector':
            auto_body = DetectorBody(*auto_body[1:])
        options = (options[0] if options else None) or {}
        return cls(epoch, crop, mode, known, catalog, scan_id, auto_body,
                   observation_live=bool(options.get('observation_live', False)),
                   retry_attempt=options.get('retry_attempt', 0) or 0,
                   preprocessing=options.get('preprocessing'))


@dataclass
class RefineRequest(_MappingAccess):
    """Re-read one tracked line in a newer frame (Live voting)."""
    kind: ClassVar[str] = 'refine'
    epoch: int
    vote: int
    frame_id: int
    frame: Any
    box: Any
    observation_live: bool = False


@dataclass
class MultiRequest(_MappingAccess):
    """Experimental multi-chip scan of one frozen frame."""
    kind: ClassVar[str] = 'multi'
    epoch: int
    scan_id: int
    crop: Any
    frame: Any
    frame_id: int
    offset: tuple
    known: tuple = ()
    catalog: Any = None
    auto_body: bool = False
    detector: Optional[str] = None
    mode: str = 'Local contrast'
    preprocessing: Optional[dict] = None


@dataclass
class ScanResultMsg(_MappingAccess):
    kind: ClassVar[str] = 'scan'
    epoch: int
    rows: list
    elapsed: float
    error: Optional[str]
    diagnostics: dict
    scan_id: int

    @classmethod
    def from_tuple(cls, result):
        return cls(*result)


@dataclass
class RefineResult(_MappingAccess):
    kind: ClassVar[str] = 'refine'
    epoch: int
    vote: int
    frame_id: Optional[int] = None
    reading: Optional[dict] = None
    error: Optional[str] = None

    @classmethod
    def of(cls, request, reading=None, error=None):
        # The frame is dropped: results must not keep video frames alive.
        return cls(request.epoch, request.vote, request.frame_id, reading, error)


@dataclass
class MultiResult(_MappingAccess):
    kind: ClassVar[str] = 'multi'
    epoch: int
    scan_id: int
    frame: Any = None
    frame_id: Optional[int] = None
    offset: tuple = (0, 0)
    chips: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    error: Optional[str] = None
    cancelled: bool = False


REQUESTS = (ScanRequest, RefineRequest, MultiRequest)
RESULTS = (ScanResultMsg, RefineResult, MultiResult)


def as_request(task):
    """Typed request from a message or a legacy tuple/dict; None stays None."""
    if task is None or isinstance(task, REQUESTS):
        return task
    if isinstance(task, tuple):
        return ScanRequest.from_tuple(task)
    if isinstance(task, dict):
        return (MultiRequest if task.get('kind') == 'multi' else RefineRequest).from_mapping(task)
    raise TypeError(f'Unknown OCR request: {type(task).__name__}')


def as_result(result, default='scan'):
    """Typed result from a message or a legacy tuple/dict."""
    if isinstance(result, RESULTS):
        return result
    if isinstance(result, tuple):
        return ScanResultMsg.from_tuple(result)
    if isinstance(result, dict) or hasattr(result, 'keys'):
        kind = result.get('kind', 'refine' if default == 'scan' else default)
        return (MultiResult if kind == 'multi' else RefineResult).from_mapping(result)
    raise TypeError(f'Unknown OCR result: {type(result).__name__}')
