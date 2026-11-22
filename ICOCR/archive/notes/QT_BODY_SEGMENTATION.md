# YOLOv8 IC body segmentation — Qt integration

- The bundled `models/ic_body_segment.onnx` (YOLOv8n-seg) is used in the existing OCR worker on each scan when **Detect component body before OCR** is enabled.
- Input: BGR frame converted to RGB, 640×640 aspect-preserving letterbox, NCHW float32 /255.
- Outputs: `[1,37,8400]` boxes/class/mask coefficients and `[1,32,160,160]` mask prototypes.
- Score threshold 0.35; box IoU NMS threshold 0.45. Masks are decoded, cropped to their detections and converted to source-image contours. Both box and mask are available to OCR crop logic.
- For single-chip scanning, the largest in-ROI high-confidence detection is used; for multi-chip scanning all full-frame detections are passed to `read_chips` with the original ROI offset. If model returns none or cannot load, the existing geometric locator is used.
- The model path is editable at Settings > Data and documentation > Body segmentation model; other model paths remain separate.
- ONNX Runtime selects the CUDA provider when available, falling back to CPU; this does not change the separately initialized OCR engine. Inference occurs on OCR worker, not the camera preview thread.
- Original source files and the Tkinter application remain unchanged except for bundled model files.

## Limitations

- Tested with synthetic ONNX output tensors and data contracts; not yet validated with Windows camera images.
- The original model metadata states `accuracy_validated: false`.
- Detection runs at scan frequency rather than every video frame. A full-frame manual scan may be needed to find all bodies.
- Manual ROI can still override automatic detection.
