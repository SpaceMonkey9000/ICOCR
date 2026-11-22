# ICOCR test13 — PySide6 migration workbench

## Launch

1. Install Python 3.11 (64-bit).
2. Run `setup_qt_windows.bat` (CPU) or `setup_qt_windows.bat cuda` (NVIDIA GPU; needs compatible CUDA runtime).
3. Run `run_qt_windows.bat` or `run_qt_windows.bat cuda`.
4. The original Tk application is unchanged and is still launchable with `launch.py`.

## Connected test13 engines

- Camera enumeration, DirectShow/MSMF capture, image loading, full-resolution JPEG capture.
- Focus-peaking overlay and its original sensitivity/colour/opacity algorithm.
- Snapshot scanning via original `OCR`, `body_scan.read_with_body`, and database-first `scan_result.build_scan_result`.
- Original SQLite ICDB `Catalog`; shared DATA location is reused, not replaced.
- Original package classifier and package-group reference choice, when weights are installed in the shared DATA folder.
- ICDB reference lookup and SVG/raster pinout rendering through the original reference modules.
- Selected-region scan, technician choice among readings, basic cyclic live scan, freeze, zoom and fit.
- Original Tkinter UI and source kept for regression comparisons.

## Limitations — not yet feature parity

This migration is a functional integration workbench, **not a full replacement** for the original Tk UI. The following test13 subsystems are not yet ported:

- Real-time tracking/voting/verification, sleep/rescan policies and scene guards (the Qt "Live recognition" mode is periodic full snapshot OCR, not the original algorithm).
- Multi-chip scanner and detector-assisted body cropping.
- Rules editor, advanced recognition and preprocessing settings, model-selection tools.
- Detailed diagnostics, technician-confirmation logging, original session-history window, manual edit/correction UI.
- Complete pinout UI conveniences, remembered manual reference selection, status and detailed selection evidence.
- Full test13 preferences restoration/persistence for the Qt controls.

Existing core modules are not rewritten. Any behaviour difference must be treated as a porting issue until compared with the Tk build.

## Validation

Python syntax compilation checked. No Windows runtime, camera, or full OCR/ICDB integration test can be executed in the current environment because PySide6 and the OCR runtime packages are unavailable. The operator must perform functional comparison on the intended Windows machine.
