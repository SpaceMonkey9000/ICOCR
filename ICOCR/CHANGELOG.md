# Changelog

All notable changes to ICOCR. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Releases are listed newest
first.

## [0.9.0-beta.1] - Unreleased

First beta of the PySide6 (Qt) application. It replaces the Tk interface and
summarises builds 0.9.0-qt1, 0.9.0-qt2 and the Qt revisions after them.

### Added

- Qt main window with Identify, History and Diagnostics tabs, and a tabbed Settings
  dialog.
- New preview pipeline: resizing, focus peaking and overlay tracking run in a worker
  thread that waits for camera frames.
- Outlines of the selected marking and chip body that follow the board on live video,
  registered on every frame so they cannot drift.
- Chip body detection with the bundled YOLOv8n-seg model, drawn as a four-corner
  outline; click a detected chip to select and scan it.
- Scan mode setting: single chip or multiple chips.
- **Prototype: OCR only inside detected IC bodies** (off by default).
- **Sleep live OCR when the scene is unchanged**, with an adjustable idle time.
- Double-click a reading to choose it yourself and add it to History.
- History tab with its own pinout and package choice, **Search datasheet**, **Open in
  ICDB**, **Add to ICDB** and **Clear history**.
- Zoomable, pannable pinout viewers on Identify and History.
- Light and Dark graphite themes matching ICDB, dark Windows title bars, and an option
  to invert pinouts in dark mode.
- Settings for the shared DATA folder, saved photos, models folder, package model and
  body segmentation model.

### Changed

- The OCR engine is created once per session and warmed up in the background, so the
  first scan no longer waits for it.
- Scan or Enter pressed during a scan is queued; a running live scan gives way to it.
- A manual scan keeps the previous outlines until its result replaces them.
- Overlay labels show the part and its function, and keep their size at every zoom.
- Single-clicking a reading no longer opens a web search; use **Search datasheet**.
- All tests are in `tests/` and run with `pytest tests`.
- Documentation rewritten for the Qt application: README, user guide,
  troubleshooting, rules and developer notes.
- `shared_data.py`, `data_lock.py` and `reference_images.py` are now identical in ICDB
  and ICOCR, checked by `tools/check_shared_files.py` and a shared contract test.
  Seeding the OCR model files moved to `ocr_runtime.py`.
- `qt_window.py` split into the `ui/` package (about 1,800 lines down to 380); no
  change in behaviour.

### Fixed

- Memory leak: every finished live scan kept its full-resolution frame.
- Live recognition rescanned a frozen frame every 1.6 seconds and overwrote manual
  results.
- The DATA lease is now taken before start-up writes rules, folders or the log.
- Closing waited too little for camera threads that were still stopping.
- The Models folder setting did not select the package classifier.
- The saved package-model path was not restored.
- Escape un-maximised the window instead of only leaving full screen.
- Space and Enter were swallowed by a focused button.
- A scan result arriving after the camera or image changed was shown.
- Tests that use the rules gave different results depending on run order.

### Removed

- The Tk interface, its launchers and every module only it used, including live
  tracking and voting, the trained chip detector and the Tk panels.
- **Correct marking** and **Confirm reading**, and the confirmed-reading CSV.
- Six-theme stylesheet; replaced by the two ICDB themes.
- Tk documentation and per-revision notes; the notes are kept under `archive/`.

## Earlier releases

Releases up to 0.9.0-qt2 are in
[archive/CHANGELOG-0.9.0-qt2-and-earlier.md](archive/CHANGELOG-0.9.0-qt2-and-earlier.md).
