# Weak-prefix ranking test 5

Includes all test 4 fixes.

Case 015: SI4BT is a broad two-letter prefix hint with a one-digit run; VP1050 is a stronger unfamiliar marking. Broad configured prefix_hints with two leading letters and no run of three digits now carry weak_prefix_hint / weak_family_hint. They retain their syntax label and remain candidates, but do not receive the same family priority or family-pattern ranking feature as strict syntax. The legacy rule choice consequently follows the stronger marking and no longer double-counts the weak prefix hint. Strict family syntax, longer numeric identifiers, and trusted database priority remain intact. No names are hardcoded to case 015, no OCR text is altered, and no database identity is inferred.

Validation: 42 tests pass with the bundled modular rules, including four new tests for case 015, trusted database priority, strict/long-numeric syntax, and isolated weak candidates. The older short-prefix test now accounts for ST being optionally configured as a retained joining prefix; configured prefixes remain unselectable alone.

Replayed all 64 captured cases with a common bundled rule snapshot and database entries reconstructed from exported matches: only case 015 changes, from SI4BT / unknown identity to VP1050 / unknown identity. Fresh image OCR and the complete installed database were not rerun.

Extract into a separate folder and use existing settings/database. No configuration reset or database additions are required. Roll back by using the previous folder.
