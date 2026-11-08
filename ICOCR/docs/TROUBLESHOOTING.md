# Troubleshooting

## Setup and launch

Run setup from the new release folder. CPU: `setup_windows.bat cpu`. CUDA:
`setup_windows.bat cuda`. Both use the Windows Python Launcher for Python 3.11.
A failed setup prints the failing dependency or diagnostic command; retain that
output. The launcher uses only local environments or an explicit ICOCR_PYTHON
path; obsolete sibling-folder discovery has been removed.

If both environments exist, the GPU environment is selected first. Force CPU
inference with `run_windows.bat run --device cpu`. To select the CPU environment
itself, set ICOCR_PYTHON to its absolute `Scripts\python.exe` path.

## GPU

**Settings → Tools** shows the active OCR processor; a CPU fallback there means
CUDA is not in use, and `DATA/ICOCR.log` gives the reason. CUDA execution requires
a compatible NVIDIA driver and the pinned ONNX/CUDA/cuDNN dependencies installed
by the GPU setup (the GPU installer bundles them). The application loads the NVIDIA DLLs on Windows.
Do not install CPU and GPU ONNX Runtime distributions together in one environment;
they provide the same Python module. Re-running the appropriate setup removes
both distributions from that environment before reinstalling the selected one.

A CUDA request in the normal application may fall back to CPU. Read the runtime
status and log for the reason. Device selection and real-time performance must be
checked on the target Windows machine.

### CUDA slower than CPU

RapidOCR 1.4.4 asks cuDNN to benchmark every convolution algorithm
(`EXHAUSTIVE`) for each new input size. Selection and body-crop sizes change
between scans, so the GPU re-tuned on almost every scan. ICOCR now uses
`HEURISTIC` for the OCR and chip-detector CUDA sessions; the runtime label in
Settings → Tools shows the active mode. To compare modes, set the variable before
starting, for example:

```bat
set "ICOCR_CUDNN_SEARCH=EXHAUSTIVE"
run_windows.bat run --device cuda
```

Accepted values are `HEURISTIC` (default), `DEFAULT` and `EXHAUSTIVE`.

## Camera

Close other applications using the same capture device if opening fails. Re-select
the device, try the other backend, or request a lower resolution/frame rate. MJPG
support depends on the capture device. Stop and restart after changing formats.

## Missing or wrong markings

Select one chip closely enough to exclude unrelated board text without cutting
characters off. Check focus, lighting and glare. Diagnostics distinguishes no
OCR text, rejected readings, conflicts and weak database evidence.

Compare Fast scan on/off and body cropping on/off on the same saved image.
A chip outline is not proof of a correct OCR crop. Detector-generated selections
have lower measured accuracy on the bundled labelled set than the manual
selections; body detection remains experimental. An unsuccessful cropped scan
retries the full selection once, so those scans take longer.

After the initial retry budget, unresolved live targets retry every five seconds.
An explicit Scan starts another acquisition. Matching does not repair character
confusions such as D/0 or I/1. An asterisk identifies multiple catalogue variants
or descriptions, not recognition certainty.

## Database and reports

Use the Component Database Builder schema, then Reload database after changing
it externally. The catalogue is not bundled. Open data folder exposes the log
and confirmed-reading snapshots for diagnosis. Session history is cleared when the app
closes; click logs and saved matches persist separately.

## Configuration defaults active (0.8.3.9)

A startup warning names each missing/invalid JSON file and the invalid field.
Run `run_windows.bat config-check` for the same diagnosis without loading OCR.
Correct the file and restart. The loader does not overwrite your edits. A bad
file uses that file's complete bundled defaults, while other valid files remain
active. Root-level `marking_brands.json` and `line_weights.json` are no longer read;
use the new files documented in [config/README.md](../config/README.md).
