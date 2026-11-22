# Package classifier integration — test8

Based on ICOCR_selection_recheck_test7. Includes the trained package model from
the supplied 20261114_173050_1be420 run, exported from best.pt with ICTRAIN 0.7.0.

## Running

1. Extract this complete archive into a separate application folder.
2. Run run_windows.bat using the existing ICOCR environment, or setup_windows.bat
   for a new environment. Runtime dependencies are unchanged; PyTorch is not needed.
3. Open Settings > Recognition. Classify package type is enabled by default.
4. Select one complete package, including its leads, and scan. The package and
   confidence appear below the snapshot. Diagnostics includes all three scores,
   the crop bounds, coordinate space, model filename, and classification time.

The supplied models/package_classifier.onnx and .json are ready to use; no model
export or import is required. A DATA/models/package_classifier.onnx takes priority
when present. Import / select package classifier accepts another ICTRAIN whole-package
ONNX export with its matching JSON sidecar. Model validation checks its kind,
preprocessing, class mapping dimensions, input shape, probabilities, and SHA-256.
The selected model and enabled flag are saved with the normal ICOCR preferences.

## Pipeline

IC body detection -> original package pixels with context -> package classifier.
OCR uses its existing body crop and recovery logic. The classifier is invoked
once per completed full scan, including Live acquisition/verification scans,
and once for each chip in multi-chip mode. Line-only rereads reuse the displayed
scan's package result rather than classify a text-line crop.

The package crop uses upright bounds around the detected body, enlarged by 25%
on each side. It uses original frame pixels when available, so an OCR selection
does not cut away the extra context. It never uses the rectified or masked OCR
body image. Multi-chip classification also uses the unmasked source region.
Without a usable body, the current selection/individual multi-chip region is used.
That fallback must contain one complete package: a whole-board selection does
not constitute a per-chip package prediction. Padding is a heuristic and can
include neighbouring components or omit long leads; this needs camera testing.

Exact ICTRAIN preprocessing: BGR to RGB, Pillow bilinear fit within 202 x 202,
preserve aspect ratio, centre on 224 x 224 RGB fill 114, float32 divided by 255,
NCHW. This is package_letterbox_v1. No mean/std normalization or softmax applied
again: ONNX already returns class probabilities.

Classes: QF (four-sided), SOP (two-sided), TO (the training set's power/tab group).
These are broad visual groups, not exact JEDEC package identification or pin counts.
Below 0.5 confidence the result is unknown. Scores are not calibrated evidence
that an object belongs to one of the trained groups; untrained packages may
receive a confident label.

Package results are advisory. They do not change OCR ranking, database matching,
part-number selection, pinouts, or tracking/selection locking. Missing, invalid,
or failing classifiers produce a diagnostic status and OCR continues. The tiny
classifier uses ONNX Runtime CPU execution with two threads; it does not require
a separate CUDA setup or compete with OCR for GPU session initialization.

## Validation

- 71 tests passed, including 15 classifier/integration tests and existing
  selection, database, joining, and lock regressions; 15 subtests passed.
- One legacy release-layout test excluded: it requires an external sibling
  DATA/models/ic_body_segment.onnx absent from the source-only test7 archive.
  Existing chip-body detection still uses the user's shared DATA model.
- ONNX export checked against PyTorch: rtol/atol 0.001, valid probability output.
- All 108 held-out photos reproduce the user's recorded top-1 predictions:
  107 correct, 1 incorrect; max score difference 4.77e-7.
- Preprocessing matched ICTRAIN bit-for-bit across all 108 test photos.
- The same error remains SOP/8872957192_cc5034b20a_o_IC_0001.jpg -> QF.
- Actual single-scan OCR worker smoke test on the supplied board photograph:
  OCR completed and returned an advisory SOP result. This verifies execution,
  not per-chip accuracy on that whole-board photograph.
- Windows UI, live camera operation, and accuracy using detector-generated
  package crops have not been measured. Held-out accuracy above uses the supplied
  curated test crops, not the detector-to-classifier pipeline.
