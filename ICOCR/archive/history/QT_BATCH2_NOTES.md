# ICOCR test13 — Qt migration batch 2

## Scope

This archive builds on the previous `qt_full.py` migration workbench and keeps the original Tk app and recognition algorithms intact.

New Qt-side features:

- In-memory recognized-marking session history, using the original test13 deduplication and database-match upgrade policy; list review, reuse and clear.
- Explicit technician selection of a displayed reading; selections are sent to the original asynchronous `marking_clicks.csv` click writer. Selection is NOT electrical verification or a write to ICDB.
- Manual correction of the text of a selected OCR reading. Editing clears any inherited database match and pinout identity rather than inventing a new lookup result.
- A bounded, readable diagnostic summary of candidate selection and exclusions.
- Persistent Qt-only preferences (`qt_preferences.json` in shared DATA), written with an atomic replace, without replacing Tk settings.

## Still not migrated

- Original test13 tracked-line `ReadingVote` worker, independent `ScanVerification`, recovery/sleep and video scene guard. The Qt live toggle still invokes periodic full scans. **Do not interpret a repeated reading from this mode as independently verified.**
- Multi-chip selection, preprocessing/rules editing, complete diagnostics, technician-confirmed original CSV export, advanced settings, and test13 tracking UI.

## Launch

1. Extract ZIP to a new folder.
2. `setup_qt_windows.bat` for CPU, or `setup_qt_windows.bat cuda` for GPU.
3. `run_qt_windows.bat` (or `run_qt_windows.bat cuda`).

The ZIP places the scripts at its root. A previous Qt environment can be reused if compatible.

## Validation

Python compilation and the Qt-neutral history/preferences unit tests performed. PySide6, camera hardware, ONNX runtime, and Windows GUI are unavailable here: **GUI runtime and functional parity are unverified**.
