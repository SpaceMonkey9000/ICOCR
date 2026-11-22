# Short-prefix joining test 4

Includes test 3 and previous fixes.

Case 063 shows LM on one line and 2903M on the next. Existing line_tokens drops tokens shorter than three characters. The wrapped patterns also omit alphabetic prefix plus numeric-with-suffix continuations.

Changes: preserve configured two-letter alphabetic prefixes as join-only candidates; permit configured prefixes followed by 3-6 digits and 1-3 suffix letters using existing geometry, same-pass and conflict checks. Require exact database support or a unique literal database base plus suffix. No guessing missing prefixes. A complete derived join is eligible for selection; a prefix alone is not.

Validation: six new short-prefix tests pass, including full selection to LM2903M / LM2903 with synthetic OCR observations and fixture database. Previous logic, logo and wrapped-rule suites pass. Replaying 64 cases using captured candidates and database records reconstructed from exported matches produces no changes. The exported case 063 contains no LM observation, so fresh image recognition must be rerun to validate the acquisition fix; the report does not establish whether the recognizer originally read LM before token filtering.

Extract separately and keep the existing settings/database. No settings reset required. Roll back using the previous folder.
