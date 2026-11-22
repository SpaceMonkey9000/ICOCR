# Package-aware pinout selection — test9

Based on package test8, with the same trained ONNX model. No retraining, ICDB
database migration or pinout republishing is required. This build reads the
existing package labels on ICDB pinout links and groups them at runtime.

## Installation

Extract the complete archive into a separate source folder. Run run_windows.bat
with the normal ICOCR environment, or setup_windows.bat for a fresh environment.
Keep using your existing shared DATA folder. Runtime dependencies are unchanged.
Package classification remains enabled by default under Settings > Recognition.

Once a database-backed component is selected, the classifier result guides the
pinout/reference choice. Both automatic single-chip selection and confirmed Live
readings use the accepted scan's package evidence. In multi-chip mode, select a
chip reading: its own package result guides its pinout, not another chip's result.

## Groups

| Model label | Compatible package-layout families |
|---|---|
| SOP | SOP, SOIC/SO, SSOP, TSSOP, MSOP, QSOP, TSOP and related two-sided variants; DIP/PDIP/SDIP/CDIP; PowerSO |
| QF | QFP/LQFP/TQFP and related QFP variants; QFN variants; PLCC/LCC |
| TO | TO-220/247/251/252/262/263/264, TO-3P; DPAK/D2PAK/D3PAK/IPAK; SOT-223 and SOT-89 |
| Unmapped | DFN, BGA/CSP, small SOT-23/323/563-style packages, TO-92/18, unknown or blank labels |

The full families are in factory/package_groups.json. These are broad layout
compatibility groups, not claims that the model distinguishes every listed
package. In particular SOP vs DIP, QFP vs QFN, pitch, mounting style, pin count
and package suffixes are not outputs of this three-class model. Grouping a DIP
reference under SOP does not mean it was trained as an exact DIP detector.
Do not merge individual database package names or their pinouts: they remain
separate choices within each group.

## Selection rules

1. Use visual package evidence only when the result is classified, the winning
   score is at least 0.85 and its margin over the runner-up is at least 0.20.
2. Keep all references in the Package / reference dropdown. Labels show the
   mapped group and the existing pin count. Grouping limits automatic choice,
   not manual access.
3. A reliable group restricts automatic candidates to compatible package labels.
   A database package hint may resolve an exact package inside that group. A
   default belonging to a different group does not override the visual result.
4. One compatible reference is selected. Duplicate aliases pointing to the same
   image with the same pin count may also be resolved automatically.
5. Different compatible pin counts or different pinout images remain unresolved
   unless the database gives a matching exact package. A library default alone
   does not resolve that ambiguity. Example: SOP cannot decide SOIC-8 vs SOIC-16.
6. If no compatible reference exists, clear the automatic pinout and retain all
   choices for manual selection. Do not silently display an incompatible default.
7. Explicit manual selection takes priority, including selection of a reference
   outside the detected group. It is remembered for the part/manufacturer and
   observed group during the current application session. A later different
   observed group does not inherit that group's manual override.
8. Missing, disabled, unsupported or uncertain classification preserves the
   previous database/default selection behavior. The status note explains it.

The model remains fallible. Confidence thresholds do not establish exact package
or pinout correctness. Test8's held-out classification result was 107/108 on curated
package crops; the new end-to-end pinout selection behavior has no measured camera
accuracy yet. OCR identity ranking and component/database matching are unchanged.

## Editing the taxonomy

On first launch, the default mapping is copied to:

`%LOCALAPPDATA%\ICSuite\ICOCR\package_groups.json`

Existing files are preserved on later launches. The equivalent ICOCR_CONFIG_DIR
override is also respected. Change family lists, minimum_confidence,
minimum_margin or overrides there; no database edits are needed. Overrides map a
normalized full package name to SOP, QF or TO. A null override excludes the name.
Example: `"overrides": {"CUSTOM-POWER-5": "TO", "DIP-8": null}`.
Mappings are reloaded when the file changes and the reference is next updated.
Invalid configurations are logged and disable visual grouping; database selection
continues. Unknown package names never receive a substring-based guess.

## Audit and validation

PACKAGE-GROUP-AUDIT.csv covers the available ICDB_Baseline_2026_10_beta1 snapshot:

| Group | Pinout links |
|---|---:|
| SOP | 2,349 |
| QF | 105 |
| TO | 3,431 |
| Unmapped: DFN-8 | 5 |

62 of its 63 distinct package names map to a model group. This audit is of the
available baseline, not a claim about the contents of your current local database.
The mapping is applied to current pinout links when ICOCR loads them.

94 tests passed, including group parsing, unsupported packages, confidence checks,
cross-group defaults, pin-count ambiguity, manual overrides, same-part group changes,
per-chip evidence, configuration preservation and the existing test8 regressions.
One inherited release-layout test is excluded because the source-only archive has
no external sibling DATA/models/ic_body_segment.onnx. Bytecode compilation passed.
Panel selection was exercised without Tk using fake widgets and image loading;
Windows UI and live camera operation remain untested.
