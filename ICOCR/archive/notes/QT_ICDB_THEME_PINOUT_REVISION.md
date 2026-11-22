# ICDB theme adjustments for ICOCR

- Reapply native dark Windows title bars when main/settings windows become visible.
- Settings > Tools > Appearance: independent **Invert SVG pinouts in dark mode** toggle. Default: enabled; stored in qt_preferences.json. Does not modify source SVG files.
- Both Identify and History pinout viewers sample the top-left pixel of the rendered pinout and set the surrounding graphics view/scene background to match.
- The pre-tracking recognition pipeline is unchanged.
- Windows title-bar behaviour requires runtime verification on a supported Windows version; native DWM dark title bars are not guaranteed by Qt on every Windows build.
