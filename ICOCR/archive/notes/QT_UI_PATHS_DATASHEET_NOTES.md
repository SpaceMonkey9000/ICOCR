# ICOCR 0.9.0-qt1 — workspace, datasheet and paths revision

Changes relative to `ICOCR_0.9.0-qt1_Overlay_Labels_Improved.zip`:

- The Qt image viewport automatically fits the source image on window/splitter resize until the user manually zooms or pans. `Fit` returns to automatic fitting. Live preview pixmap and source-image coordinates remain separate.
- The five camera buttons are ordered **Capture / Scan / Freeze / Focus peaking / Fit**, evenly distributed and square-cornered. Button, tab panel and field corner radii were removed from both themes.
- Removed **Correct marking** and **Confirm reading** controls from the Identify tab. Their unused methods were removed in the cleanup revision.
- Single-clicking a recognised reading searches the web for the matched ICDB part number (or OCR marking) plus `ic datasheet`, URL-encoded.
- **Search datasheet** in Identify runs the same web search for the selected row. (An ICDB-URL based *Open datasheet* button was drafted but never connected; its lookup code was removed in the cleanup revision.)
- Data and documentation Settings tab now includes editable **Shared DATA**, **Saved photos**, **Models folder**, and **Package model** paths, with Browse controls.
- Photos destination takes effect immediately. Shared DATA location is written to the existing ICSuite location configuration; restarting ICOCR is required. A new DATA folder must already contain `components.sqlite` to prevent silent data loss. Existing data files are not moved.
- The Package model path is used for the ONNX package classifier; by default it is `package_classifier.onnx` in the Models folder, or the copy bundled in the application's `models` folder when the Models folder has none. The Models folder does not change RapidOCR's weights or the body segmentation model path.
- All other recognition and database algorithms remain unchanged.

## Validation
- Python compilation and source-level datasheet lookup test passed.
- Windows GUI, live camera and actual ICDB link population have not been runtime-tested.
