# Batch 5 — camera preview and overlay performance

## Changes from Batch 4

- GUI preview timer set from 70 ms (~14 Hz maximum) to 33 ms (~30 Hz requested). Actual performance remains hardware-dependent.
- Video frame is no longer unnecessarily copied a second time on every poll. `Capture` publishes new frames and does not mutate its published array.
- Preview resize switches from `INTER_AREA` to the faster `INTER_LINEAR`; the captured image and OCR input remain full-resolution.
- Overlay polygons and text items are reused instead of destroying/recreating QGraphicsItems every preview frame.
- Recognition outlines increased from 2 px to 3.5 px cosmetic width; text from 10 pt semibold to 13 pt bold with dark backing.
- Motion processing is submitted only four times per second and on resized <=640-pixel-wide frames, never 4K frames.
- The worker continues using the original test13 overlay-motion engine. Its affine translations are scaled back to full-resolution frame coordinates.
- Overlay geometry persists between tracking updates; it is hidden if tracking has not succeeded for over one second. Stale worker results over 850 ms old are ignored.
- Original source images, focus peaking behaviour, scan selection, OCR, and pinout selection are unchanged.

## Known limitations

- Live tracking is still the experimental test13 projection worker, not full test13 multi-frame voting/component tracking.
- If the camera scene changes substantially and tracking fails, existing labels fade after one second; they are not magically reidentified.
- Focus peaking remains a CPU-side preview filter and can still reduce FPS on slow systems.
- Actual Windows camera/UI FPS has not been measured or tested in this environment. Requested 30 Hz is an update limit, not guaranteed FPS.

## Run

Extract the ZIP. Run `setup_qt_windows.bat` then `run_qt_windows.bat`.
