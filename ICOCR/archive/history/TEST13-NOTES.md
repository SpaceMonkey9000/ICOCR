# Focus peaking — test13

Version: 0.8.9.9-RC3-package-choice-test13

The **Focus peaking** checkbox beside Capture image highlights fine detail across
the entire preview. It works independently of Live recognition, the selected OCR
region, detection and recognition sleep. It also works on opened/paused images.

In **Settings → Camera → Focus peaking — preview only**:

- Enable focus peaking: the same switch as the toolbar checkbox.
- Colour: Red (default), Green, Yellow or Cyan.
- Sensitivity: Low, Medium (default) or High. High shows weaker detail; Low
  restricts highlights to stronger edges.
- Opacity: 50%, 75% (default) or 100%.

Changes apply immediately without restarting capture and are remembered between
sessions. Peaking starts disabled unless enabled previously. Existing capture
folder and other preferences are retained.

Peaking is applied only to a temporary display image after preview resizing.
Full-resolution captured photos, confirmed images, snapshots and OCR input remain
clean. It uses fixed fine-detail thresholds, so defocusing reduces highlights
rather than normalizing the remaining blurred edges back into view.

This is a focus aid, not a calibrated focus measurement. Noise, scratches and
reflections can highlight too. Its appearance depends on preview size, lighting
and camera sharpening; adjust sensitivity for the subject. No focus meter or
exposure indicators are added in this build.

## Validation

- Eight focus peaking checks passed: sharp versus blurred detail, flat fields,
  sensitivity order, all colours and opacity, invalid preference fallback,
  preview toggling/paused-frame refresh, preference writeback and clean JPEG capture.
- Three existing capture-folder checks passed.
- All Python source files compile, and the application imports successfully.
- Live microscope camera performance and Windows GUI appearance require a local
  check; no physical camera or Windows desktop was available here.

Extract into a new application folder and launch as usual. Shared DATA and model
installation remain as documented for test12/test11.
