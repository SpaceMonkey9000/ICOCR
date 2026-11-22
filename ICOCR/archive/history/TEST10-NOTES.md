# Shared package model storage — test10

The package classifier now runs exclusively from the configured shared
DATA/models directory, alongside the other ICSuite models. For an installation
using the standard AppData DATA folder this is:

`%LOCALAPPDATA%\ICSuite\DATA\models\package_classifier.onnx`

Its required companion is `package_classifier.json` in the same directory.
An existing custom DATA folder / ICLENS_DATA override is respected; this change
does not relocate your database or change the shared DATA selection.

Extract this complete build into a new application folder and launch normally.
On first startup the supplied models/package_classifier.onnx and .json are
installed together into shared DATA/models. Both source files are removed only
after the destination contract and checksum pass validation. The models seed
folder is removed when empty. Runtime never loads from the application folder.

A different existing shared model/sidecar is retained without replacement.
Conflicting incomplete destinations are left unchanged and logged; OCR remains
available. Read-only application folders may retain their installation seed
files when deletion is denied, but inference still uses the shared copy.
Import / select package classifier already imports models into shared DATA/models
and continues to use that location.

The trained weights, package groups and test9 pinout-selection behavior are
unchanged. No retraining or ICDB migration is required.

Validation: 98 tests passed, including migration, sidecar transfer, preservation
of existing models, conflict handling, runtime path resolution, and test9
regressions. One inherited external body-model release-layout check was excluded.
Migration tests use temporary application/DATA folders; Windows filesystem
permissions and live camera operation remain untested.
