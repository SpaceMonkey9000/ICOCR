# ICOCR PySide6 — UI revision (after Batch 2)

This build restructures the interface of `qt_full.py` without adding recognition features.
It retains the test13 engine, the Qt Batch 2 history, correction, confirmation,
database matching, pinouts, diagnostics, and existing camera bindings.

## Layout changes

- Removed the prototype's crowded first toolbar and the Batch 2 second toolbar.
- Slim top header: camera selection, Start, Stop, Open image, Camera options, Settings.
- `Camera options` reveals video mode, backend and Refresh cameras only when needed.
- Left: large live camera/image display; underneath Capture, Scan, Focus peaking,
  Freeze, Fit; underneath those, Live recognition, Auto body, Package classifier.
- Right: Identify, Pinout, History, Diagnostics tabs, with recognition controls
  grouped rather than appended around the interface.
- Scan snapshot is now collapsed by default.
- Pinout rendering scales to the available sidebar space.
- Window dimensions and camera/sidebar splitter sizes are remembered in
  `qt_preferences.json`.
- Original `app.py` / Tk interface remains in the archive.

## Run

1. Extract the archive. Keep all files together.
2. Run `setup_qt_windows.bat` (or reuse an existing Qt environment).
3. Run `run_qt_windows.bat`.

The Qt entry point is `qt_full.py`. This UI revision has not been
verified with a Windows camera or Qt graphical runtime in this environment.
