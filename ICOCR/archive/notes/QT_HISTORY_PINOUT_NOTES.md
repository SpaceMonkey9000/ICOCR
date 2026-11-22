# Qt History pinout panel

- Selecting a reading in History now renders its linked ICDB pinout below the details.
- Uses the existing package/reference selection logic and the same cached SVG/raster loader as Identify.
- Respects the active light/dark theme and rescales on window resize.
- Does not switch to Identify or change the active recognised reading.
- Clears the preview when history is empty or a reading has no available linked ICDB reference.

No recognition or camera code was modified.
