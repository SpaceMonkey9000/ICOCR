# ICOCR History → ICDB handoff

- History action order: Search datasheet, Open in ICDB, Add to ICDB, Clear history.
- Open in ICDB requires an existing selected database match.
- Add to ICDB works on matched and unmatched history entries. Verify the editable
  part number in ICOCR; ICDB then opens its component editor and stages the entry.
- ICDB supports `--open-part PART` and `--add-part PART` command-line arguments.
  The supplied shared DATA directory is also passed via `--data`.
- The Add action is not an automatic save. ICDB's global Save commits the draft
  and Revert discards it. Duplicate saved components open instead of being added.
- This version still launches an additional ICDB process; existing-window IPC
  is a separate future change.
- The OCR source image and package metadata are not yet transferred.
