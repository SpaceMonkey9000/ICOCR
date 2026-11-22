# ICOCR PySide6 minimal UI revision

Based on the previous test13 PySide6 UI Revision. No OCR, capture, ICDB, or package-selection algorithms were changed.

## Main window
- One compact top row: camera selector, Start, Stop, Open image, Settings.
- Camera preview and one action bar: Capture, Scan, Focus peaking, Freeze, Fit.
- Only one bottom QStatusBar; additional camera and scan-status rows removed.
- First Identify tab includes recognized markings and the pinout reference/image.
- The "Selected reading" label is removed. Its underlying evidence field is retained as collapsible **Identification details**, closed by default.
- History and Diagnostics remain in separate tabs.
- Nonessential options, excluded-reading checkbox, scan snapshot, and extra package/confirmation status labels are removed from the visible workspace while corresponding functionality remains in its original code path.

## Settings dialog
Five tabs:
1. Camera settings: video mode, capture backend, peaking colour, sensitivity, opacity, refresh devices.
2. Recognition: live recognition, body detection, fast/targeted scanning, package classification, model selection, excluded readings.
3. Rules: explanation that original Tk rules editor is not ported; does not pretend to edit rules.
4. Data and documentation: current shared data folder and documentation capability status.
5. Tools: reload ICDB and open data folder.

Settings are applied on OK and saved to the existing `qt_preferences.json`; Cancel does not apply changes to scan configuration. Refresh cameras and Tools actions are immediate commands.

## Validation
- Python syntax compilation passed.
- Not runtime-tested in Windows or with Qt because PySide6 is unavailable in the build environment.
- No new documentation or recognition features added.
