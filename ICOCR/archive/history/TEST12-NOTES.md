# Automatic choice within a detected package group — test12

Several compatible pinout options no longer block automatic display.

Selection order:

1. An explicit manual reference choice for this component and detected group.
2. A matching exact database package within the detected group.
3. The default reference within the remaining compatible options.
4. The first remaining compatible reference in the library's stable order.

Example: SOP with SOIC-8, TSSOP-8 and DIP-8 references selects the compatible
default, or the first compatible reference when none is marked default.
A QFP default cannot win against a reliable SOP prediction. All options remain
available in the dropdown. A reliable group with no compatible reference still
leaves automatic display empty. Uncertain classification preserves the previous
database selection behavior.

This is a default reference choice, not inference of pin count or exact package.
Diagnostics identifies the choice rule and number of compatible alternatives.
This supersedes test9's requirement for manual selection among multiple
compatible pinouts. Group mapping, thresholds, OCR identity selection and the
trained model are unchanged.

No startup model movement occurs. Keep package_classifier.onnx and its matching
package_classifier.json in shared DATA/models, as in test11. Extract this build
into a new application folder and launch run_windows.bat normally.

97 tests passed, including three compatible options with and without a default,
exact-package priority, cross-group exclusion and manual override. One inherited
external body-model release-layout check was excluded. Windows UI/live camera
behavior remains untested.
