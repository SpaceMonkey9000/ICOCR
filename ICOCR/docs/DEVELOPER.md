# ICOCR developer notes

## Code layout

| Area | Modules |
| --- | --- |
| Entry point and start-up | `qt_full.py` (configuration, logging, DATA lease, start-up errors), `app_state.py`, `user_paths.py`, `project_paths.py`, `version.py` |
| Main window | `qt_window.py` (`MainWindow`: start-up, settings, preferences, theme, close handling), `qt_theme.py`, `qt_user_preferences.py` |
| Main window parts (`ui/`) | `main_layout.py` (widgets), `camera.py` (camera, images, preview, freeze, capture), `scanning.py` (scans, overlay, readings list), `pinout_panel.py` (Identify pinout), `history_panel.py` (History and ICDB hand-off), `workers.py` (database, engine and scan threads), `settings_dialog.py`, `app_paths.py` (`APP_ROOT`, bundled models) |
| Picture and preview | `qt_view.py`, `qt_scan_region.py`, `qt_preview.py`, `capture.py`, `focus_peaking.py`, `documentation.py` (captures) |
| Overlay | `overlay_tracker.py` (frame-to-frame registration, no Qt), `qt_recognition_overlay.py`, `app_presenters.py` |
| OCR | `ocr_core.py`, `ocr_runtime.py` (CUDA set-up and CPU fallback), `ic_preprocessing.py`, `snapshot_selection.py`, `multi_chip.py` |
| Chip bodies and packages | `ic_body_detector.py` (YOLOv8n-seg), `body_locator.py` (geometric fallback), `body_scan.py`, `package_classifier.py`, `package_pinouts.py` |
| Reading selection | `scan_result.py`, `line_ranking.py`, `selection_evidence.py`, `readings_list.py`, `marking_rules.py`, `marking_aliases.py`, `marking_context.py`, `prefix_rules.py`, `confusion_matching.py`, `database_rules.py` |
| Configuration and rules | `config_loader.py`, `config_defaults.py`, `rule_modules.py`, `tuning_schema.py`, `diagram_defaults.py`, `factory/` |
| Catalogue and pinouts (read-only) | `component_catalog.py`, `icdb_references.py`, `logic_diagrams.py`, `qt_pinout_view.py`, `reference_images.py` |
| ICDB hand-off | `qt_icdb_bridge.py`, `qt_session_history.py` |
| Shared with ICDB | `shared_data.py`, `data_lock.py`, `reference_images.py` (see Shared files below) |

## Running from source and tests

```bat
setup_qt_windows.bat
.venv-qt\Scripts\python -m pip install -r requirements-dev.txt
.venv-qt\Scripts\python -m pytest tests
```

`tests/conftest.py` puts the application folder on the import path and points
`ICOCR_RULES_DIR` at `factory/rules` before any test imports the rule modules. Run
the tests through pytest; plain `unittest` does not load that file.

`tests/test_qt_window.py` runs the whole window offscreen against a synthetic moving
camera. `tests/test_overlay_tracker.py` checks tracking accuracy. The package
classifier and release tests need the bundled models in `models/`.

`tools/check_config.py` validates the configuration without loading OCR models.

## DATA contract with ICDB

ICOCR and ICDB are separate programs that share one DATA folder. ICOCR only reads
what ICDB writes.

- **Location:** `shared_data.data_directory()`: `ICLENS_DATA`, then
  `%LOCALAPPDATA%\ICSuite\data_location.json`, then the older
  `%LOCALAPPDATA%\IC_Tools\data_location.json` (read only), then the default. Both
  applications save to the `ICSuite` file with `shared_data.save_directory()`.
- **Lock:** `data_lock.DataLease`, a shared lock on `DATA\.icsuite.lock`, taken before
  start-up writes anything into DATA.
- **Database:** `DATA\db\components.sqlite`. ICOCR reads `components`, `entries`,
  `sources`, `pinout_assets` and `pinout_links`.
- **Pinouts:** SVG or raster files referenced by `pinout_assets.path`, relative to
  DATA. ICDB writes generated diagrams to `DATA\pinouts\generated`.
- **Hand-off:** **Open in ICDB** and **Add to ICDB** start ICDB with
  `--data <DATA> --open-part <part>` or `--add-part <part>`, using ICDB's
  `.venv-qt` Python. No shell is involved.

### Shared files

These files are shared and must be byte-identical in ICDB and ICOCR:

| File | Contents |
| --- | --- |
| `shared_data.py` | Finding and saving the DATA folder, and the database path |
| `data_lock.py` | The lock on the DATA folder |
| `reference_images.py` | Loading SVG and raster pinouts |
| `tools/check_shared_files.py` | Compares the shared files with the other application |
| `tests/test_shared_data.py` | Tests of DATA folder resolution |
| `tests/test_data_contract.py` | ICDB publishes into a temporary DATA folder; ICOCR reads it back |

Change a shared file in one application, then copy it to the other.
`python tools/check_shared_files.py` (with the other application next to this one,
or its folder as an argument) fails if any copy differs. The two shared tests do the
same check, and run the contract test, when the other application is next to this
one; otherwise they are skipped.

## Design decisions

- **No multi-frame voting.** Live recognition is a periodic full scan of the selected
  region. Voting and verification across frames lowered correct identification in
  testing, so they were left out of the Qt application.
- **Evidence, not identity.** Rules propose syntax, prefixes and corrections; they
  never establish a component's identity or pick a pinout on their own. Exact
  database matches keep precedence.
- **Rules are data.** Rule modules in `DATA\rules` are JSON with validated kinds;
  no Python is executed from DATA. Rules load once at start-up.
- **The preview never waits for OCR.** Camera, preview processing and overlay
  tracking run off the GUI thread. The OCR engine is created once and warmed up in
  the background.
- **The overlay is registered per frame** against the scanned frame, so it cannot
  drift. Large jumps are recovered by phase correlation.
- **Body detection runs at scan time,** not on every video frame.
- **Captures and scans use full-resolution frames;** the preview is downscaled.
- **CUDA errors fall back to CPU once,** logged with the reason, unless strict mode is
  requested. Input errors are not retried.

## Things to fix later

- `qt_icdb_bridge.py` only starts ICDB from source; it must find `ICDB.exe` for the
  packaged builds.
- Some tests write to the real settings folder; they should use a temporary
  `ICOCR_CONFIG_DIR`.
- Phase 3 moved code without changing it. `MainWindow` is split into mixins
  (`CameraMixin`, `ScanMixin` and so on) that share the window's attributes. Turning
  them into separate controller objects with their own state is a later step.
- Tests replace `ui.camera.Capture`, `ui.workers.shared_ocr` and
  `ui.workers.read_with_body`; keep those names if the code moves again.
