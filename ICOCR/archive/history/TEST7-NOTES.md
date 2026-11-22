# Selection recheck test 7

Based on test 5. Includes the accepted previous fixes and excludes the rejected C515C rule from test 6.

Purpose: stop consistent recognition of the wrong printed line from being treated as proof that the correct line was selected.

Ranking: when an unverified, unstructured later-line rule choice faces a >=0.95 OCR earlier mixed marking within 0.03 OCR score, with no unresolved conflict, withhold the initial-choice ranking bonus. The competing earlier marking may pass the fitted threshold only when it was already eligible under the existing selection rules and has a >=0.35 line-score advantage after removing that circular bonus. Strict syntax, strong unfamiliar marking shapes, database evidence, numeric protection, and other decisions retain their existing handling. No specific chip names or manufacturer suffix rules are added.

Live verification: line-vote agreement no longer sets the stop-rescanning flag for unidentified markings. Existing full-chip verification remains limited to three attempts at 1.2-second intervals (plus processing time), using the Scan verification setting. An unidentified challenger can replace an unidentified incumbent only after two distinct captured frames return it, with the incumbent also present in each full-chip result, high OCR, first-line block evidence, no conflicts, and a >=0.35 same-scan score advantage. It cannot replace a database-backed incumbent. Exact database upgrades keep their existing path. Missing/failed scans reset the challenger streak. Rejected checks preserve the displayed evidence through the existing tracker resolve(None) path. Manual choices and invalid tracking states remain protected by existing scheduler/acceptance checks.

Diagnostics: withheld initial-choice bonuses appear in line_reason; verification logs include incumbent, candidate, reason, confirmation count and all candidate rows.

Validation: 51 tests pass, including nine new ranking/sequence/vote/scheduling tests. All 64 retained-observation selections and identities are unchanged in before/after replay with the bundled rule snapshot and database records reconstructed from exported matches. The new image example selects HC14AG instead of AKADJ37 in a synthetic two-line test using the supplied text/confidences. Its raw OCR geometry was not provided. Fresh camera OCR, the actual captured video sequence, tracking/display behaviour on a real camera, and the complete installed database have NOT been tested here.

Run from a separate extracted folder with existing settings/database. Keep Scan verification enabled for bounded full-chip challenger checks. No settings reset is required. Use the test 5 folder to roll back; no rule files are added in this build.
