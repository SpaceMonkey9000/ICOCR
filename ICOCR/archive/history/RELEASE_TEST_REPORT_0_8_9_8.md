# ICOCR 0.8.9.8 RC1 — offline integration report

Baseline: ICOCR 0.8.9.7 RC1 with the 76 supplied active modular rule definitions, body detector ONNX and metadata, OCR models and supplied component database.

## Code fix
- `ConfigSnapshot(directory=...)` now reads `directory/settings.json` rather than using the global default `SETTINGS_FILE`. This repairs configuration directory override behavior for snapshot instances and test tooling.
- Version updated to 0.8.9.8-RC1.

## Executed tests
Run with `python tools/test_release_0898.py` from `ICOCR`.

1. Fresh isolated configuration and DATA initialization: PASS.
2. Loads 76 modular rules, with no validation errors: PASS.
3. Repeat initialization preserves edited rule bytes and custom settings: PASS.
4. No obsolete `ICOCR/config/` directory created: PASS.
5. Disabling `ranking.lines` through its JSON module disables ranking on a new process: PASS.
6. Malformed modular JSON produces a diagnostic entry: PASS.
7. Body-detection ONNX plus valid JSON sidecar present: PASS (presence only, no inference).
8. Python module byte compilation and AST parsing: PASS.

## Not tested / release blockers
- Full Tk Windows UI, camera capture, actual body detector ONNX inference.
- OCR inference, manufacturer-logo model accuracy, candidate ranking on representative samples, ICDB lookup and SVG rendering.
- Windows frozen executable startup and startup self-test.
- UI rules-edit/save workflow and recovery from a write interruption.
- True shared installation with a separately installed ICDB build.

Do not characterize this candidate as runtime validated. Hardware- and OS-dependent tests remain mandatory before 0.9 beta.
