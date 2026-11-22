# ICOCR database-first test build 1

Based on 0.8.9.9-RC3. Source distribution, **not** a compiled Windows executable.

## Changes

- Trusted database matches survive unrecognized or noisy OCR frame votes.
- Equal-strength conflicting database identities remain on the incumbent instead of switching solely based on vote count.
- A stronger database candidate may replace a weaker incumbent once its OCR frame vote is confirmed.
- OCR observations and conflicts are preserved on re-annotation.
- Technician selection updates the live vote view and overlay immediately, where live tracking geometry is valid.
- All existing scene invalidation, tracking constraints, and multi-chip selection remain in place.
- `identity_resolution` and `voted_ocr_key` added to live rows for debugging.

## Limitations

- Catalog membership is not a guarantee of identity; ambiguous entries are not treated as strong matches.
- Conflicting trusted identities require a new independent scan or technician intervention; line voting alone cannot resolve them.
- No camera or GUI integration test was run in this environment.
- Existing single-chip live overlays require active tracking and valid projection; snapshot-only results do not automatically produce tracking geometry.

## Quick test

1. Run as usual with `run_windows.bat` in a separate copy of this folder, with your existing database and models installed according to README.
2. Scan a known IC and enable Live.
3. Confirm that subsequent OCR misreadings do not erase a trusted database function.
4. Choose another candidate from the right panel; confirm the overlay follows the technician choice while tracking stays valid.
5. Move to a different IC; confirm the scene/track resets before any old identity is shown.
