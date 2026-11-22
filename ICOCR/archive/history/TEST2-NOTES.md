# ICOCR split-marking test 2

Based on ICOCR_database_first_test1.zip. Its recorded source hashes match the supplied ICBENCH run.

Copy this folder separately, then retain your existing launch procedure and database/settings paths. No settings reset is required. Roll back by using the original folder.

Changes:
- Reconstruct adjacent aligned HC/HCT/AHC/AHCT logic fragments, including ON/CON logo contamination.
- Recognise abbreviated HC/HCT markings ending in A against an exact 74-series database base.
- Correct O to zero only in the numeric field of these logic families, with OCR >= 0.90, no unresolved conflicts, and an exact database base.
- Withhold ambiguous incomplete low-current regulator prefixes such as LM78L. Do not infer a voltage from DOSACM.

Expected cases: 010 HC14A -> 74HC14; 012 HCT273A -> 74HCT273; 046 AHCOO -> AHC00 -> 74AHC00 if that exact database entry exists; 029 abstains rather than selecting incomplete LM78L.

Validation: four regression tests use actual retained image geometry and OCR observations, with controlled database fixtures. Eight database priority tests pass. Thirteen wrapped-rule tests pass; one full-pipeline test was skipped because OpenCV is unavailable. Fresh image OCR and the full 57-case ICBENCH run have not been rerun. The 74AHC00 database fixture establishes behaviour when present, not its presence in your installed database.
