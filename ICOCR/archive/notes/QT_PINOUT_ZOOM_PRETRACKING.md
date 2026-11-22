# Pinout zoom on pre-tracking qt2 baseline

Baseline: `ICOCR_0.9.0_qt2_History_Pinout_Themes.zip`.

Only the Identify and History pinout viewer controls are replaced with Qt graphics views. No `ReadingVote`, `ICTracker`, or tracking-phase files are added.

- Mouse wheel zoom around cursor (0.15–30x relative to fitted scale).
- Left/middle drag to pan.
- Double-click to fit.
- Auto-fit when resizing until the user manually zooms.
- Selecting another ICDB package reference fits the new pinout.
- Both original identification selection and historical package selection are preserved.
- ICDB reference files are never modified.

Testing: static compile and source regression checks. Graphical Windows interaction has not been tested.
