# ICOCR troubleshooting

## Setup and start

From source, run setup in the application folder: `setup_qt_windows.bat` for CPU or
`setup_qt_windows.bat cuda` for an NVIDIA GPU. Both need Python 3.11 (64-bit) through
the Python Launcher and create `.venv-qt` or `.venv-qt-gpu`. If setup fails, keep its
output: it names the dependency that failed. Start with `run_qt_windows.bat` or
`run_qt_windows.bat cuda`.

A start-up failure is shown in a dialog and written to
`%LOCALAPPDATA%\ICSuite\ICOCR\startup-error.log`.

**"Close ICOCR, ICDB and any DATA updater, then retry".** A DATA updater holds the
DATA folder. Wait for it to finish, or close it.

## Configuration warnings

At start-up ICOCR checks its settings and rule files. A warning names each missing or
invalid file and the invalid field. An invalid file is replaced by its bundled
defaults for that session; the other files stay active, and your file is not
overwritten. Fix the file and restart.

To check the configuration without starting the OCR engine:

```bat
.venv-qt\Scripts\python tools\check_config.py
```

## GPU

**Settings → Tools** shows the active OCR processor. If it says CPU, CUDA is not in
use, and `DATA\ICOCR.log` gives the reason. CUDA needs a compatible NVIDIA driver and
the GPU setup. Do not install the CPU and GPU ONNX Runtime packages in one
environment; re-running setup removes both before installing the one you chose.

To force the CPU in the GPU environment, set `ICLENS_DEVICE=cpu` before starting.

### CUDA slower than CPU

cuDNN can benchmark every algorithm for each new input size, and selection sizes
change between scans. ICOCR therefore uses the `HEURISTIC` search mode by default.
To compare, set the mode before starting:

```bat
set "ICOCR_CUDNN_SEARCH=EXHAUSTIVE"
run_qt_windows.bat cuda
```

Accepted values are `HEURISTIC` (default), `DEFAULT` and `EXHAUSTIVE`.

## Camera

- Close other programs that use the same camera.
- Choose the camera again, try the other back end in Settings → Camera settings, or
  choose a lower resolution or frame rate. Changes apply when the camera next starts.

## Missing or wrong readings

- Select one chip closely: the whole marking, as little other board text as possible.
- Check focus (Focus peaking helps), lighting and glare.
- The Diagnostics tab shows whether OCR found no text, rejected a reading, found a
  conflict or had weak database evidence.
- Try the same saved image with **Fast scan** and **Detect component body before
  OCR** switched on and off.
- **Prototype: OCR only inside detected IC bodies** reads nothing if no body is
  detected. Switch it off for chips the detector misses.
- Matching does not repair character confusions such as D/0 or I/1 on its own; the
  OCR correction rules handle known cases.
- An asterisk means the catalogue has several variants or descriptions for the part,
  not that the reading is uncertain.

## No pinout, or an old one

ICOCR shows pinouts that ICDB has published. After changing a pinout in ICDB, save and
publish it there, then use **Settings → Tools → Reload database** in ICOCR.

## Open in ICDB or Add to ICDB does not work

ICOCR starts ICDB from its source folder, which needs `.venv-qt` (run ICDB's
`setup_qt_windows.bat`). If ICOCR asks for the ICDB folder, choose the folder that
contains `icdb_qt.py`. Installed `ICDB.exe` builds are not supported yet.

## Reporting a problem

Include the version from the window title, `DATA\ICOCR.log`, the Diagnostics text for
the scan and, if possible, a capture of the frame.
