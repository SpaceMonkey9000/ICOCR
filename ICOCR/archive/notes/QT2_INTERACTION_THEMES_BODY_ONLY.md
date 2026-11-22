# ICOCR Qt2 — Recognition interactions, themes and body-only OCR

Based on the user-provided `ICOCR_0.9.0-qt2_Fixes.zip`.

## Main window

- Single click in Recognised markings: selects the reading, updates pinout/details. No browser launch.
- Double click: opens the usual `<part number> ic datasheet` Google search.
- The additional bottom-right camera/performance label is removed. The single-line status bar remains.

## Settings → Recognition

- **Prototype: OCR only inside detected IC bodies** (off by default).
- When enabled, the ONNX body detector runs on the source frame and the scanner processes detected bodies only. It skips the ordinary multi-chip full-region OCR discovery. OCR recovery outside the detected body is disabled in this mode. The detector's cropped body is still subject to the existing recognition and selection rules.
- Scanning with no detections produces no OCR readings and a status message; the geometric full-image fallback is not invoked in this experimental mode.
- In this prototype, up to the existing `multi_chip.MAX_CHIPS` (10) bodies are scanned, strongest first; detection and OCR still run as part of scan workers, not at video FPS.
- Disabled by default to preserve the previous recognition workflow. Disable it if body detection misses a chip or you need to read unencapsulated markings.

## Settings → Tools → Appearance

Dark, Graphite, Slate, Modern light, Windows classic, Warm light.
Themes are persisted using the existing preference file. Dark variations invert SVG previews in memory as before; original files are unchanged. Theme styling does not affect the recognition engines.

## Verification

Source compilation and 24 unittest cases passed (23 passed, one Qt GUI test skipped because PySide6 is not present on the test machine). Actual Windows video/CUDA/GUI operation has not been tested.
