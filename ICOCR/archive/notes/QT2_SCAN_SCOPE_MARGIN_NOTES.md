# Qt2 scan scope and selected-body motion margin

## Fixes

- Recognition settings now offer **Scan mode: Single chip / Multiple chips**. This replaces the old manual-only multi-chip checkbox. The chosen mode is used by both manual and live scans, and is saved through the existing `multi_enabled` preference for backward compatibility.
- **Prototype: OCR only inside detected IC bodies** is independent of scan mode. In single-chip/body-only mode, the ONNX detector chooses one eligible body; if none is detected, no OCR is performed. Full-selection recovery is disabled for that mode. In multi-chip/body-only mode, all eligible detected bodies are individually scanned (up to the existing limit).
- Selecting a detected chip retains its exact four-edge package outline, but expands the scan ROI by **15% of detected body width/height on each side, at least 16 original-image pixels**, clipped to the frame. This tolerates slight chip movement between selection and scanning without changing segmentation geometry or masking other pixels in body-only mode.

## Interaction

- Click a visible IC body to select its expanded ROI and initiate a scan. Right-click in the preview resets the selection, as in the existing Qt interaction.
- Settings > Recognition > Scan mode chooses single or multiple chip processing.
- Settings > Recognition > Prototype: OCR only inside detected IC bodies controls whether non-body OCR discovery is allowed.

## Limitations

- The scan margin is fixed for this prototype. Large movement can still move a chip outside the ROI. Motion-aware ROI tracking is not implemented.
- In single-chip mode with body-only OFF, no model-body match can still trigger the original geometric/full-selection path, preserving previous fallback behaviour.
- PySide6/Windows camera and CUDA tests have not been performed in the execution environment.
