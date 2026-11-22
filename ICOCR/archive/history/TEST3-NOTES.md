# ICOCR logo conflict test 3

Includes all changes from split-marking test 2.

Case 028: permit the retained HEF/HCF marking to resolve a conflict with precisely TL + that marking. This requires strong OCR on both readings, matching physical text regions and direction, literal database support for the retained reading, and no trusted separate identity for the extended reading. Other conflicts continue to veto selection. The original conflict and an explicit rule trace remain in the exported diagnostics. The existing join.logo switch controls the new handling.

Validation: 32 tests passed (six new conflict tests, four logic reconstruction tests, fourteen wrapped-rule tests, eight database priority tests). Replayed selection for all 57 cases before and after with database records reconstructed from exported matches: only case 028 changed, from abstention to HEF4538BT / HEF4538B. This is a selection replay using captured OCR, not a fresh OCR benchmark or verification against the complete installed database.

Extract into a separate folder and run with the existing settings and database. No settings reset is required. Use the previous folder to roll back.
