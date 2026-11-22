# ICOCR 0.9.0-qt1 — Overlay label revision

Changes limited to recognition overlay presentation (`qt_recognition_overlay.py`):

- Preserve both the part identification and the function description returned by the original test13 `app_presenters.overlay_label()`.
- When a selected ICDB entry exists but the scan result lacks `function_summary`, recover the source-recorded description from its `entry_function` or `component_function` fields.
- Use a 15 pt bold Segoe UI heading, 12 pt medium description, dark opaque label background and coloured border.
- Wrap description to at most two display lines with ellipsis for longer entries.
- Increase recognition outline width to 3.5 screen pixels. Preserve Qt item reuse and tracking from the uploaded build.
- Keep labels as graphics items independent of saved image content, respecting zoom.

Tested: `python -m unittest tests.test_qt_overlay_labels tests.test_qt_overlay_geometry` (5 passed), plus Python syntax compilation.

Not tested: visual rendering and camera operation on Windows; PySide6 unavailable in the build environment.

No changes to OCR, ICDB, matching, camera or tracking algorithms.
