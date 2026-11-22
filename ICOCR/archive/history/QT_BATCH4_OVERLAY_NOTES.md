# ICOCR test13 PySide6 — Batch 4: preview recognition overlays

## Implemented

- New Qt `QGraphicsScene` recognition overlay (`qt_recognition_overlay.py`), independent of pixels saved to disk.
- Selected OCR quadrilateral and concise identification label from the existing test13 `app_presenters.overlay_label` logic.
- Detected IC body outline from `body_scan` diagnostics.
- Manual multi-chip scan outlines for each chip's selected OCR marking and detected body.
- Source-crop to full-resolution to preview coordinate conversion, preserving scroll/zoom/pan alignment.
- Uses original test13 `OverlayWorker` and `overlay_motion` to project scan geometry onto newer live frames off the GUI thread. Hides overlays when no valid motion transform is available; it does not feed transformed geometry back into OCR.
- Checkbox under Settings > Recognition: Display recognition outlines and labels on preview, persisted with Qt settings.
- Clear overlays on new scan, new image, or camera restart. Original ROI rectangle and focus peaking remain in place.

## Limitations

- Not yet the complete test13 tracking/voting/verification system. Manual and periodic live scan results can be annotated, but full voting and scene persistence are not migrated.
- For normal scans, the selected/provisional marking is displayed, not every rejected OCR diagnostic. For multi-chip scans, each returned target is displayed.
- Live motion projection is conservative; overlays may temporarily disappear when alignment fails or video changes abruptly. This is intentional to avoid showing stale coordinates.
- Hardware and Windows GUI runtime were not available in the packaging environment; static checks and coordinate unit tests passed.

## Run

Extract ZIP. Execute `setup_qt_windows.bat` and `run_qt_windows.bat` from the top-level folder.
