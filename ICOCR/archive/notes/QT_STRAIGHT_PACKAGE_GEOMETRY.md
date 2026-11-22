# Straight-edge IC body geometry revision

- The ONNX segmentation contour is converted to a **four-corner rotated minimum-area rectangle** (`cv2.minAreaRect`, `cv2.boxPoints`).
- The fitted quadrilateral is used for all detected-body overlays and click selection; it follows package rotation rather than drawing a fixed horizontal rectangle.
- `body_crop()` now retains pixels inside that four-edge quadrilateral and neutralizes pixels outside it. The irregular segmentation contour stays available as metadata but is **not** used as the OCR crop shape.
- Multi-chip detection reuses the same `polygon` corners.
- This change does not add tracking or modify scan frequency; the previously implemented multi-body selection and sleep logic remain.
- When the segmentation mask is missing or implausible, the axis-aligned detector box is used as fallback.
