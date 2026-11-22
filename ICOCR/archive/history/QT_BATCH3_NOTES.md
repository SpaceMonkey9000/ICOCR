# ICOCR test13 PySide6 — Batch 3

## Changes

- Added a Qt Rules tab based on the original `RuleSnapshot`, `save_enabled`, and test13 validation functions. Search, refresh, checkbox edits, and explicit Save rules are available. As in Tkinter, rule changes require restart.
- Added a Recognition setting for manual multi-chip scans using existing `multi_chip.read_chips` and `body_scan.read_with_body`. Multi-chip is restricted to manual scans; periodic live scanning continues using the existing single-selection path.
- Fixed close workflow: immediately stop live scheduling; mark application closing; stop camera acquisition; request cooperative OCR cancellation; wait asynchronously for OCR/DB Qt workers to finish before destroying shared database or UI objects; save preferences and close document writer after workers finish.
- Preserved original Tkinter application, recognition rules, matching, ICDB, and capture-file semantics.

## Still missing / caveats

- This is not complete test13 parity. Tk's scene tracking, recovery, multi-frame voting, independent verification, advanced diagnostics and specialized settings remain unported. The Qt live mode is periodic rescan, not the original tracking/vote pipeline.
- OCR cancellation is cooperative. If a native OCR/ONNX call does not return, the application will remain in a closing state until that call completes. Force-killing the worker thread would be unsafe; process isolation is needed for a hard-stop guarantee.
- Multi-chip Qt mode currently presents the detected chip targets through the standard candidate list rather than the full original per-chip review workflow. It is experimental.
- Rule changes only take effect after restart, consistent with original test13.
- No Windows GUI or hardware test completed in this environment because PySide6 is unavailable. Python compilation and existing Qt model tests passed.

## Start

`setup_qt_windows.bat` then `run_qt_windows.bat`, from the extracted archive root. Existing CPU/GPU environments remain separate.
