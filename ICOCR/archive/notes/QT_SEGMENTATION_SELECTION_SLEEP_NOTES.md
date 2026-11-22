# PySide6 IC body selection and live OCR sleep revision

## Body outline and crop
- The YOLOv8 segmentation adapter already returned `mask_polygon` and `body_crop()` already applied a polygon mask around the component. This revision corrects the **display** of that mask: the full-frame `mask_polygon` is used for the clickable overlay instead of the detector's rectangular box.
- A scan with a selected ROI still runs the detector against the complete camera image. Every detected body outline remains available for selecting another IC, including when OCR is restricted to the selected chip.
- Manual Scan no longer clears previous outlines before OCR has finished. The result replaces the old overlay atomically after scanning.
- Selected chip ROI is rectangular for OCR-region coordinates, while `body_crop()` keeps pixels within the detected silhouette and neutralises the exterior. A square region-selection rectangle does not mean the OCR image is unmasked.
- If the ONNX detector is unavailable or finds nothing, the old geometric body detector remains the fallback. Geometric fallback is not a multi-body inventory.
- Tracking still depends on successful image registration. The overlay can temporarily hide after the camera view changes substantially or alignment fails. Body detection itself remains scan-driven, not continuous per frame.

## Recognition idle sleep
- Added `Sleep live OCR when the scene is unchanged` under Settings > Recognition.
- `Idle time before sleep` is configurable from 10 to 3600 seconds, default 120.
- While sleeping, the camera preview continues. Periodic OCR jobs are suppressed; the next sampled scene change wakes OCR automatically. The scene is sampled using a downscaled 96x54 grayscale frame at the existing live-timer rate, with a mean absolute pixel difference threshold of 5.
- Preferences are saved and restored in `qt_preferences.json`.
- This is a new Qt idle recognition gate. It is not a port of the old Tkinter live tracker or multi-frame voting system.

## Validation
- Python compileall passed.
- Geometry and mask/ROI unit tests passed.
- Actual Windows GUI, CUDA inference and camera tests have not been run here; PySide6 and onnxruntime are not installed in the container.
