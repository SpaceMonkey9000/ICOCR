# PySide6 UI — light/dark themes

- Settings dialog has horizontal tabs at the top (Camera settings, Recognition, Rules, Data and documentation, Tools).
- Theme selection is under Settings > Tools > Appearance. Changes apply on OK and persist in `DATA/qt_preferences.json`.
- Light theme displays ICDB SVG pinouts in their existing white-background rendering. Dark theme inverts the RGB-rendered SVG preview only; original SVG and ICDB data are untouched. This also inverts any colours used within the SVG; it is a literal inversion, not semantic recolouring. Raster diagrams remain unchanged.
- Camera content is never inverted.
- Original Tkinter application and underlying matching algorithms are unchanged.
- Syntax checks only; no local PySide6 runtime or Windows camera validation.
