"""Optional CUDA setup for RapidOCR 1.4.4; explicit session checks and CPU fallback."""
import logging
from pathlib import Path
import os


# Retain handles for the process lifetime: closing them removes DLL search paths.
_dll_handles = []
_dll_libraries = []
_dll_ready = False


def sessions(engine):
    return {
        'detection': engine.text_det.infer.session,
        'orientation': engine.text_cls.infer.session,
        'recognition': engine.text_rec.session.session,
    }


def providers(engine):
    return {name: session.get_providers() for name, session in sessions(engine).items()}


CUDNN_SEARCH_MODES = ('HEURISTIC', 'DEFAULT', 'EXHAUSTIVE')


def cudnn_search():
    """cuDNN convolution algorithm search used for CUDA sessions.

    RapidOCR 1.4.4 hard-codes EXHAUSTIVE, which benchmarks every algorithm for
    each new input shape. Detection and recognition shapes follow the selection
    and body crop, so almost every scan paid that cost on the GPU. HEURISTIC
    picks an algorithm without benchmarking. ICOCR_CUDNN_SEARCH overrides it.
    """
    value = os.environ.get('ICOCR_CUDNN_SEARCH', 'HEURISTIC').strip().upper()
    if value not in CUDNN_SEARCH_MODES:
        logging.warning('Ignoring ICOCR_CUDNN_SEARCH=%r; expected one of %s',
                        value, ', '.join(CUDNN_SEARCH_MODES))
        value = 'HEURISTIC'
    return value


def cuda_provider(options=None):
    """CUDA provider entry with ICOCR's cuDNN search mode (for direct sessions)."""
    return ('CUDAExecutionProvider', dict(options or {}, cudnn_conv_algo_search=cudnn_search()))


def patch_rapidocr_cuda_options():
    """Override RapidOCR's CUDA provider options before its sessions are built.

    Idempotent; the search mode is read each time a session is created, so a
    changed ICOCR_CUDNN_SEARCH applies to the next engine.
    """
    from rapidocr_onnxruntime.utils import infer_engine
    session_class = infer_engine.OrtInferSession
    if getattr(session_class, '_icocr_cuda_options', False):
        return
    original = session_class._get_ep_list

    def _get_ep_list(self):
        return [cuda_provider(options) if name == 'CUDAExecutionProvider' else (name, options)
                for name, options in original(self)]

    session_class._get_ep_list = _get_ep_list
    session_class._icocr_cuda_options = True


def _setting(key, default):
    """Tuning value, or ``default`` when the key is absent from the snapshot.

    The configuration snapshot is built at import and always holds the bundled
    defaults, so the only expected failure is a missing key (a stripped or
    patched snapshot in tools/tests). Anything else is a real error.
    """
    from config_loader import tuning
    try:
        return tuning(key)
    except KeyError:
        return default


def runtime_errors():
    """Exception types that indicate an ONNX Runtime / CUDA execution failure.

    Used to decide whether a failed CUDA scan may be retried on CPU. Input
    errors (ValueError, TypeError, ...) are deliberately not included: they
    would fail on CPU too and must not demote the GPU session.
    """
    errors = [RuntimeError, MemoryError]
    try:
        from rapidocr_onnxruntime.utils.infer_engine import ONNXRuntimeError
        errors.append(ONNXRuntimeError)
    except ImportError:  # other RapidOCR layout; RuntimeError still covers our own checks
        pass
    try:
        from onnxruntime.capi import onnxruntime_pybind11_state as state
        errors.extend(getattr(state, name) for name in
                      ('Fail', 'EPFail', 'RuntimeException', 'EngineError', 'InvalidArgument',
                       'InvalidGraph', 'NoSuchFile', 'NotImplemented')
                      if isinstance(getattr(state, name, None), type))
    except ImportError:
        pass
    return tuple(errors)


def thread_count(limit=4):
    """ONNX Runtime intra-op threads: leave two cores for camera, tracking and UI."""
    return max(1, min(limit, (os.cpu_count() or 4) - 2))


def configure_session_options(options):
    """Idle worker threads sleep instead of spinning (tuning ocr_runtime.allow_spinning).

    Spinning keeps cores busy between the many small OCR/detector calls and
    starves the camera, tracking and Tk threads on small CPUs.
    """
    spin = '1' if int(_setting('ocr_runtime.allow_spinning', 0)) else '0'
    options.add_session_config_entry('session.intra_op.allow_spinning', spin)
    options.add_session_config_entry('session.inter_op.allow_spinning', spin)
    return options


def patch_rapidocr_session_options():
    """Apply configure_session_options to every RapidOCR session (idempotent)."""
    from rapidocr_onnxruntime.utils import infer_engine
    session_class = infer_engine.OrtInferSession
    if getattr(session_class, '_icocr_session_options', False):
        return
    original = session_class._init_sess_opts

    def _init_sess_opts(config):
        return configure_session_options(original(config))

    session_class._init_sess_opts = staticmethod(_init_sess_opts)
    session_class._icocr_session_options = True


def configure_detection(engine):
    """Text-detector input size and normalisation (0.8.4.3).

    * ocr_runtime.det_limit_side_len = N > 0 caps the detector input's longest
      side at N px and never enlarges it. RapidOCR's default enlarges the
      shortest side to 736 px, on top of ICOCR's own probe scaling (up to 2x),
      so a wide line crop reached ~5x its source size. 0 keeps the default.
    * mean/std as float32: the normalised tensor is bit-identical (scaling by
      0.5 is exact) but no float64 intermediate image is allocated.
    """
    det = getattr(engine, 'text_det', None)
    if det is None or not hasattr(det, 'get_preprocess'):
        return
    import numpy as np
    for name in ('mean', 'std'):
        value = getattr(det, name, None)
        if value is not None:
            setattr(det, name, np.asarray(value, dtype=np.float32))
    side = int(_setting('ocr_runtime.det_limit_side_len', 0))
    if side > 0:
        from rapidocr_onnxruntime.ch_ppocr_det.utils import DetPreProcess
        det.limit_type, det.limit_side_len = 'max', side
        det.get_preprocess = lambda max_wh: DetPreProcess(side, 'max', det.mean, det.std)


def cuda_options(engine):
    """Provider options actually applied to each OCR session (diagnostics)."""
    result = {}
    for name, session in sessions(engine).items():
        try:
            result[name] = session.get_provider_options().get('CUDAExecutionProvider', {}).get(
                'cudnn_conv_algo_search', '')
        except Exception:
            result[name] = ''
    return result


def prepare_cuda_dlls(ort):
    """Discover installed NVIDIA DLLs from wheel records, including newer layouts."""
    global _dll_ready
    if _dll_ready:
        return
    if os.name != 'nt':
        ort.preload_dlls(directory='')
        _dll_ready = True
        return
    from importlib import metadata
    import ctypes
    dlls = []
    cudnn_version = ''
    for dist in metadata.distributions():
        name = (dist.metadata.get('Name') or '').lower().replace('_', '-')
        if not name.startswith('nvidia-'):
            continue
        if name == 'nvidia-cudnn-cu12':
            cudnn_version = dist.version
        for file in dist.files or ():
            if str(file).lower().endswith('.dll'):
                path = dist.locate_file(file).resolve()
                if path.is_file():
                    dlls.append(path)
    # PyInstaller collects wheel DLLs into one private directory.
    import sys
    if getattr(sys, 'frozen', False):
        dlls.extend((Path(sys._MEIPASS)/'cuda').glob('*.dll'))
    directories = sorted({str(path.parent) for path in dlls})
    for directory in directories:
        _dll_handles.append(os.add_dll_directory(directory))
    # cuDNN's own lazy LoadLibrary calls also need the process PATH.
    # No system or user environment variables are persisted.
    if directories:
        os.environ['PATH'] = os.pathsep.join(directories + [os.environ.get('PATH', '')])
    bundle_cuda = Path(sys._MEIPASS)/'cuda' if getattr(sys, 'frozen', False) else None
    ort.preload_dlls(directory=str(bundle_cuda) if bundle_cuda and bundle_cuda.is_dir() else '')
    tensor = [p for p in dlls if p.name.lower() == 'cudnn_engines_tensor_ir64_9.dll']
    if cudnn_version.startswith('9.26.') and not tensor:
        raise RuntimeError('cuDNN '+cudnn_version+' is missing cudnn_engines_tensor_ir64_9.dll; reinstall nvidia-cudnn-cu12 in .venv-gpu')
    # ORT 1.22's preload list predates this cuDNN sub-library.
    for path in tensor:
        try:
            _dll_libraries.append(ctypes.WinDLL(str(path)))
        except OSError as exc:
            raise RuntimeError('Cannot load '+str(path)+' or one of its dependencies: '+str(exc)) from exc
    _dll_ready = True


def create_engine(device=None, strict=False):
    import onnxruntime as ort
    # Keep local snapshot processing free of ONNX Runtime telemetry events.
    ort.disable_telemetry_events()
    from rapidocr_onnxruntime import RapidOCR
    device = (device or os.environ.get('ICLENS_DEVICE','auto')).lower()
    if device not in ('auto','cpu','cuda'):
        raise ValueError('Device must be auto, cpu or cuda')
    # Never oversubscribe small CPUs; the GUI and tracking threads also need cores.
    # 0.8.4.3: at most cpu_count-2 threads, and idle threads sleep (see configure_session_options).
    from shared_data import ocr_model_paths
    from project_paths import DATA
    options = dict(intra_op_num_threads=thread_count(4), inter_op_num_threads=1, **ocr_model_paths(DATA))
    patch_rapidocr_session_options()
    reason = ''
    if device != 'cpu':
        try:
            if hasattr(ort,'preload_dlls') and 'CUDAExecutionProvider' in ort.get_available_providers():
                prepare_cuda_dlls(ort)
            if 'CUDAExecutionProvider' not in ort.get_available_providers():
                raise RuntimeError('CUDA provider is not installed in this environment')
            patch_rapidocr_cuda_options()
            engine = RapidOCR(**options,det_use_cuda=True,cls_use_cuda=True,rec_use_cuda=True)
            active = providers(engine)
            if not all(v and v[0]=='CUDAExecutionProvider' for v in active.values()):
                del engine
                raise RuntimeError('One or more OCR sessions fell back to CPU; check driver/CUDA DLLs')
            for session in sessions(engine).values():
                session.disable_fallback()
            configure_detection(engine)
            search = cuda_options(engine)
            mode = ', '.join(sorted({v for v in search.values() if v})) or 'unknown'
            return engine, dict(device='cuda',label='NVIDIA CUDA enabled (cuDNN search: '+mode+')',
                                providers=active,cudnn_conv_algo_search=search,reason='',
                                ort_version=ort.__version__)
        except Exception as exc:
            if strict:
                raise RuntimeError('GPU initialization failed: '+str(exc)) from exc
            reason=str(exc)
            logging.warning('GPU unavailable; using CPU: %s',reason)
    engine=RapidOCR(**options,det_use_cuda=False,cls_use_cuda=False,rec_use_cuda=False)
    configure_detection(engine)
    return engine,dict(device='cpu',label='CPU'+(' (GPU fallback)' if reason else ''),
                       providers=providers(engine),reason=reason,ort_version=ort.__version__)
