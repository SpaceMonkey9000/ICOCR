# History datasheet action

- Replaced History > Use reading with Search datasheet.
- Uses selected history record's ICDB part number, falling back to recorded marking.
- Opens a browser search for `<part number> ic datasheet`.
- Disabled when no valid history part is selected.
- History selection still updates the history pinout and does not modify the active Identify reading.
- Test results: 29 tests run, 1 skipped; Python compilation passed.
