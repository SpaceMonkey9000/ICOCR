# Manual package model placement — test11

Startup package-model migration has been removed. ICOCR does not copy, move or
delete package model files automatically. Runtime loads the default only from
the configured shared DATA/models folder.

Move these two supplied files from this archive's models folder:

- package_classifier.onnx
- package_classifier.json

Place both together in your existing shared DATA/models folder. For a standard
AppData DATA installation this is:

`%LOCALAPPDATA%\ICSuite\DATA\models`

Keep using your existing DATA location if it is customized. Do not create a
different DATA folder merely for this model. If the files are already there,
no additional move is needed. Then launch run_windows.bat normally.

The trained weights and test9 package-aware pinout selection are unchanged.
Missing or invalid model files produce a classifier-unavailable diagnostic;
OCR continues. The explicit Import / select package classifier action remains
available for importing future models when requested through the UI.

95 tests passed. One inherited external body-model release-layout check was
excluded. Windows UI/live camera behavior remains untested.
