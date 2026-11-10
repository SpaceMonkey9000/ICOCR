# ICOCR 0.8.9.9-RC3 validation

- Capture destination checks: 3 passed, using actual OpenCV JPEG encoding/decoding. Covers default/saved paths, folder creation, numbering across restart/older PNGs, confirmed log separation and destination changes with queued saves.
- Existing wrapped-rule regressions: 14 passed.
- Existing clean-install and rule-edit integration checks: 2 passed.
- All Python modules compiled and parsed successfully.

Windows folder redirection, native folder chooser, full GUI, camera hardware and frozen executable startup were not exercised in this Linux environment. Source ZIP only; no Windows executable was rebuilt. Supplied OCR/rule changes are preserved.
