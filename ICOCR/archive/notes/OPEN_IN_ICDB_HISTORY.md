# Open in ICDB — ICOCR History integration

Updated alongside the ICDB Revision 19 source supplied in this conversation.

- History tab gains **Open in ICDB**, enabled only for entries with a selected matched ICDB part number.
- First use: choose the updated ICDB installation directory if it is not in the recognized sibling location. ICOCR saves the chosen path in `DATA/qt_preferences.json`.
- Requires an installed ICDB `.venv-qt` environment (`setup_qt_windows.bat`).
- Launches ICDB's own virtual environment directly with `--data <ICOCR DATA> --open-part <matched part>`; uses no shell interpolation.
- ICOCR does not write to the database or modify its matching logic.
- Initially launches a separate ICDB instance for each request; live IPC to an existing ICDB window is not implemented.
- This is an explicitly selected History operation, not a live recognition control.
