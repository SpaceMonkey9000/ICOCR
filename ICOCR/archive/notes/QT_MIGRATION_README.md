

## Qt UI / body selection update (November 2026)

- Datasheet control now searches `<selected part> ic datasheet`; it does not depend on an ICDB URL.
- Package model file is configured only in Data and documentation; its enable switch remains in Recognition.
- Removed explanatory help text from Data and documentation.
- Camera starts automatically when the main window opens. Live recognition starts automatically only when enabled in saved Settings.
- The toolbar includes an Image folder button, opening the configured saved-photo directory.
- Clicking an existing detected-body outline selects that body as OCR ROI and starts a manual scan. When another scan is active, one follow-up scan is queued. Body click coordinates include the live overlay motion transform.
- This does not enable an external trained cropping detector: the packaged build uses the existing geometric detector and OCR-based multi-chip path.
