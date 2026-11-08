# 0.8.9.9-RC2

- Restore VERSION export required by app.py; keep APP_VERSION as a compatibility alias.
- Frozen self-test now imports the real application before testing OCR and Tk.

# 0.8.9.9-RC1

- Canonical ICSuite shared DATA location preference, with legacy IC_Tools fallback.
- Identical shared path/model helper with ICDB 0.8.3-RC1, including UTF-8 BOM support.
- Replace stale primary README with current deployment/settings paths.

# ICOCR release notes

All ICOCR changes in one file, newest first, followed by the history of its predecessor IC Lens. Each entry describes behaviour at the time of that release; later entries supersede earlier rules, paths and defaults.

## ICOCR 0.8.9.6-RC1 (beta release candidate)

First public beta release candidate. Recognition, matching and rules are identical to 0.8.9.6; packaging only:

- Version is now 0.8.9.6-RC1 (window title and Windows file version). `version.py` previously still said 0.8.9.4.
- Development files removed: tests, validation data and replay tools, benchmark and fitting tools, pytest/dev requirements and old validation reports.
- `manage.py` keeps the `run` and `config-check` commands. `setup_windows.bat cuda` now checks that ONNX Runtime reports the CUDA provider instead of running the old GPU sample scan, whose sample image was not shipped.
- Release notes from the README, `ICOCR_CHANGELOG.md`, `docs/CHANGES.md` and the separate RELEASE files merged into this file.
- Can be built into CPU and GPU Windows installers and portable zips with the ICSuite build kit.

## ICOCR 0.8.9.6 — Ordering-code suffix matching

- **New:** ordering-code suffix matching (switch `match.ordering_suffix`). A reading of the form PART-SUFFIX now matches PART when PART is an exact database name. Example: "PIC18F252-1S0E3" (OCR of "PIC18F252-I/SO" plus the e3 lead-free mark) → PIC18F252. Also covers e.g. MCP2551-I/SN, ATMEGA328P-PU, ATTINY85-20PU, LCMXO2-1200HC-4TG144C. Shown as "Suffix match (unverified)".
- **Limits:** the base part must be at least 5 characters and contain both letters and digits. The suffix may be up to 10 letters, digits or slashes, with at most one extra hyphen. No match if the database has hyphenated variants of the same base (e.g. TCAN1042-Q1), since those are distinct parts, or if database records for the base have conflicting descriptions.
- `DATA\rules\match.ordering_suffix.json` enables the switch.

## ICOCR 0.8.9.5 — Rule tweaks

### Matching
- Letter-suffix matching: a numeric-only base part (7805 in "7805A", "7805CT", "79L05A") is now accepted when the printed text matches a strict device-family rule. Previously the base had to be 5+ characters and contain a letter, so "7805A" selected nothing.
- Resistor codes: short numbers are only treated as resistor values when they are valid standard codes: 3-digit E24 (103, 472), 4-digit E96 / 1% E24 (4701, 4991, 1002), 0 / 000 jumpers. The exclusion reason now shows the value ("Resistor code 472 = 4.7 kΩ").
- Short numbers that match a strict family rule (7805, 7912) are no longer excluded. Other short numbers (555, 2904, 7400, date codes) remain excluded as "possible resistor value or date code".
- New switch `exclude.resistor_codes`: excludes R-notation (4R7, 0R1, 49R9) and EIA-96 codes (01C, 68X). Turn off if SOT-23 marking codes are added to the database later.

### Rules (DATA/rules)
- Fixed: hint rule_7 (Infineon) no longer matches Xilinx XC2C/XC2S parts.
- Extended existing rules: 74/54 logic (more families: LCX, LVX, VHC, AUP, HCU, FCT, CBT, S, H, L; maker prefixes CD, MC, M, TC, HD, MM, DM, NLV, IDT; 1G–3G), DS (DS18B20/DS18S20/DS1822/DS28EA00), LM (any one-letter LM sub-family: LMR, LMP, LMH, LMZ, LMT…), Motorola/Freescale (MC9S08, MC56F), Infineon (SAF-/SAB-/SAL- temperature-grade prefixes).
- New hint patterns: PIC/dsPIC, AVR, TI TMS320/TMS570/MSP430/TM4C, Xilinx, Altera/Intel, Lattice, Renesas R5F, NXP LPC/S32K, ST SPC5.
- New strict patterns: 78/79 regulators, CMOS 4000 (incl. Toshiba TC4), optocouplers (TLP, MOC, H11, FOD, HCPL, ACPL, LTV, 4N/6N, PC817, EL817, CNY17, PS25xx), ST L-series, triacs/SCRs (BTA, BTB, BT13x, Z0xxx).
- New spaced-join rules: "L 7805 CV", "CD 4017 BE".
- Prefix hints split into three files (max 64 values each): `syntax.additional_prefixes.json` (original 23 + 41 new), `syntax.additional_prefixes_2.json` (VIPER, ATMEGA, ATTINY, DSPIC) and `syntax.additional_prefixes_short.json` (29 two-letter prefixes; higher false-positive risk, can be disabled separately).
- `syntax.prefixes.json` restored to the original 45 prefixes.
- MOSFET short markings: prefixes FQA, FQPF, NTP, NTD, NTB; suffix G.
- Brands: added TEXAS, LINEAR, XILINX, ALTERA, LATTICE, ALLEGRO, DALLAS, IOR, FREESCALE, MOTOROLA, MICREL and others.
- Origin words: added VIETNAM, MALTA, MOROCCO, COSTA, RICA, CZECH and others.

## ICOCR 0.8.9.4 — adjustable sidebar

The right sidebar now has three independently sized sections: Snapshot, Recognised markings with component information, and Pinout with its package selector. Drag either horizontal divider to redistribute the space. Each section has a minimum size to keep its controls accessible.

Divider proportions are saved when a drag finishes and restored at startup. They scale with window height. Settings → Tools → Reset layout restores the default proportions. Preferences are stored in sidebar_layout.json beside the existing user settings; no DATA database migration is required.

Component information now occupies four scrollable lines instead of reserving eight lines. The readings list expands within its section and has vertical and horizontal scrolling. Long information remains available by scrolling. Recognition updates do not alter the divider positions. The snapshot preview fits its resized section, including its detection outlines.

The previous pinout cleanup, removed Edit reading button, modular rules and ICDB integration remain in place.

Extract into a new application folder and use the existing DATA folder. No new dependencies are required.

## ICOCR 0.8.9.3 — sidebar cleanup

- Removed the Edit reading button from the main sidebar.
- Removed source/manufacturer text and the click-to-enlarge hint beneath the pinout. Clicking the image still enlarges it; reference source remains in the enlarged view.
- Normal pinout status is blank. Relevant states use short messages: Previous reading, Package mismatch, No pinout available, Image unavailable, or Select a reference.
- Pinout heading and status each reserve one fixed-height line, with font-measured truncation. Text changes no longer resize the image area.
- Tightened sidebar padding and snapshot status space. The upper section requests room for its contents; the pinout expands into the remaining space. Upper-section scrolling remains available for smaller windows.
- All 0.8.9.2 rules and ICDB common-pinout lookup behavior are retained.

Extract into a separate application folder and launch normally using your existing shared DATA folder. No new dependencies or database migration are required.

## ICOCR 0.8.9.2 — additional database rules

Built from 0.8.9 with its individual rule checkboxes. The old source is retained separately. ICDB common-pinout connections and lookup code are unchanged.

### New rules

| Checkbox | Behavior |
| --- | --- |
| Additional literal part prefixes | Adds syntax hints for TLE, ADM, UCC, INA, ADUM, ISO, DRV, TSV, TDA, NJM and additional power-device prefixes. Does not invent missing prefixes. |
| Additional 74-series abbreviations | Suggests exact database names for LS, ALS, F, AC, ACT, AHC, AHCT and LVC abbreviations. Keeps families separate; does not also strip package suffixes. |
| Missing 2S transistor prefix | Suggests transistor-function database entries for A/B/C/D/J/K markings. Includes KSA/KSC alternatives for A/C markings. PCB-reference exclusions remain effective: ambiguous C1815-style tokens appear as suggestions, not automatic selections. |
| Database-backed short MOSFET markings | Supports one- to three-digit leading numbers, database prefixes, and suffix variants. Requires MOSFET function evidence and rejects driver/controller/IGBT/regulator descriptions. Entire stems must match: 4N60 never matches 14N60. A printed suffix must match exactly. |
| Missing hyphens and spaces | Suggests names differing only by hyphens/spaces. Retains decimal points and slashes. Keeps all colliding names as separate suggestions. |

All new name-recovery rules produce unverified suggestions, even if only one candidate exists. Exact names take precedence. Existing 0.8.9 logic-alias and explicit MOSFET-prefix rules retain their behavior. Independent rules may overlap: to disable all short MOSFET suggestions, disable both MOSFET modules.

The rules are data-only JSON (`kind: database_rule`, a validated recipe and values list); their bounded operations live in database_rules.py. No executable plugins or scan-time file reads are added. Lookup indexes are built once per loaded catalog. The migration marker records this additive update so intentionally deleted modules are not recreated on later launches.

### Database checks

Checked against the supplied database of 17,472 names:

- 50N06-: all seven CS/DFP/FQP/HFP/MTP/RFP entries, including FQP50N06L.
- 4N60: six MOSFET candidates; 10N60: eleven MOSFET candidates, excluding IGBT entries.
- C1815: 2SC1815 and KSC1815; A1015: 2SA1015 and KSA1015.
- K2611: 2SK2611; LS244/F244/AC244: matching 74-series families.
- AD71244: AD7124-4. LM1117-1.2 retains its decimal point during annotation.

The database was opened read-only. No pinout or common-connection data was changed.

## ICOCR 0.8.9

### Changes

- 51 stock JSON rule modules stored in the existing shared DATA/rules folder.
- Non-destructive first-run migration of existing external rule settings, including custom lists and disabled patterns.
- Settings → Rules: grouped checkboxes, search, refresh, folder access, explicit save and restart notice.
- Shortened MOSFET markings such as 50N06- produce database suggestions with the allowed prefixes; raw OCR text and significant suffix variants are preserved. No inferred full part is automatically confirmed.
- Existing matching/joining/context operations can be toggled alongside the external rules. Original family-rule order is preserved.
- Data-only extension formats, validation/duplicate detection, diagnostic hashes and stale-edit checks.

## ICOCR 0.8.8 — Review fixes

Bug-fix and performance release. No new dependencies beyond an explicit PyYAML
pin (already installed transitively). Default tuning is unchanged: the optional
speed-ups `ocr_core.full_shared_detection` and `ocr_runtime.det_limit_side_len`
remain off; see config/TUNING_REFERENCE.md to try them.

### Fixes

- **Confirmed readings log the right scan.** The readings list keeps its own
  snapshot, scan id and mode. Rejected Live verification scans and in-flight
  rescans no longer replace them, so `confirmed.csv` and the sidebar preview
  always match the list you clicked.
- **Failed confirmation writes can be retried.** A reading is marked logged only
  after the CSV row is written. If `confirmed.csv` is locked (e.g. open in
  Excel) the status says so, the orphan JPEG is removed and clicking again retries.
- **No exit hang** when a documentation write is stuck (e.g. a network share).
- **GPU stays on GPU:** only ONNX Runtime/CUDA errors trigger the CPU fallback;
  input errors such as a too-small selection no longer switch the session to CPU.
- Missing/failed detector model is logged once instead of every frame.
- `matching.max_affix_chars = 0` no longer breaks body-numeric lookups.
- Alias-index cache is stored as JSON instead of pickle (old caches are removed
  and rebuilt automatically on first start).
- One invalid pinout asset row no longer hides all pinout references; ICDB
  edits made in quick succession are detected more reliably (WAL header check).
- Live recovery reads respect the remaining time budget; multi-chip failures
  are logged with tracebacks; detector box mapping is consistent at image edges.
- Windows launchers only use a Python environment whose setup completed (or,
  for older installs, one where onnxruntime imports). A failed `setup cuda`
  no longer leaves an unusable `.venv-gpu` preferred over a working `.venv`.
- `launch.py` validates `ICLENS_DEVICE`; "standard" preprocessing no longer
  writes `null` to preprocessing.json; Space capture is not swallowed after a
  dialog had focus; ICOCR.log rotates (5 MB × 3).
- Clearer error when DATA's `data_location.json` is malformed (shared with ICDB 0.4.8).

### Performance

- Video display downscale of 4K frames ~3× faster (≈8 ms → ≈2.6 ms per frame) with
  slightly better image quality.
- Idle-sleep thumbnail ≈5× cheaper for 4K frames.
- Candidate conflict resolution up to ~14× faster with many text lines
  (identical results).

### Cleanup

Removed unused imports and the stray `cuda-before-rollback.txt`; PyYAML pinned;
Pillow bound aligned with ICDB (<13); ICLens → ICOCR in requirement headers.

### Upgrade

Extract to a new folder and keep your DATA folder and configuration. Existing
`.venv`/`.venv-gpu` environments keep working (`run_windows.bat` checks them);
running `setup_windows.bat` again is optional and adds the completion marker.

## ICOCR 0.8.7 — Stage 1

- Display SVG pinouts linked in ICDB, including preview and enlarged view.
- Keep the existing package/reference selector and remembered selections.
- Disable tooltip binding/display for main-window controls; retain Settings help.
- Read SVG references through the existing shared database; no package inference
  or automatic electrical-equivalence matching is introduced.

## ICOCR 0.8.5

### Changes

- Sleep keeps the last pinout/reference visible while OCR, tracking and detector work pause. The camera preview remains live. Wake invalidates the old scene and resumes recognition.
- The inactivity default is 120 seconds. Existing saved timeouts are preserved; Settings > Camera changes them.
- Clicked readings display Selected. Edited readings display Clarified. Confirmation logging retains its existing CSV format and meaning: a user choice, not independently verified identity.
- Right-click on the camera preview restores the default centred selection box, cancels any drag, clears stale tracking and wakes recognition.
- Standard snapshot and initial Live scans now actually use Original first. Targeted retries use the alternate treatment, avoiding a duplicate Original pass. Unresolved Live attempts retain treatment alternation, now beginning with Original. Explicit saved snapshot preprocessing policies remain intact.
- Camera capture starts once after the startup enumeration completes. Stop or opening an image cancels pending startup. Refresh does not automatically restart capture. Missing cameras and failed enumeration do not cause repeated open attempts.
- Added control tooltips for camera startup, selection, shortcuts, sleep, preprocessing, readings, logs, references and settings. Renamed Targeted Original fallback to Targeted treatment fallback to reflect both treatment directions. The saved setting key remains compatible.
- New diagnostic output uses DATA/ICOCR.log. Existing ic_lens.log files are left intact. Confirmed readings, click-history and capture filenames are unchanged.

### Upgrade

Use this application folder with the existing shared DATA and per-user configuration. No database conversion is required. Custom sleep timeouts and preprocessing policies are not overwritten. To use the new preprocessing default when an explicit policy is already saved, select Standard in Settings > Recognition > Snapshot preprocessing.

This archive contains application source, launch scripts and tests. It does not contain a compiled Windows installer, the parent installer build kit, CUDA binaries or the shared component database/pinouts.

## ICOCR 0.8.4.9

- Inactivity sleep with a 30-second default, adjustable in Settings > Camera.
- Thumbnail motion detection, exposure-offset compensation, manual wake, retained models, worker invalidation.
- ICOCR config and UI/preprocessing JSON use per-user AppData; existing files are preserved.
- Support shared databases in DATA/db as well as the legacy DATA root; pinout images resolve relative to DATA.
- Application icon and frozen startup/self-test entry point.
- Shared DATA lease prevents concurrent writes by the new data updater.
- Private bundled CUDA DLL discovery and pinned Windows build tooling in the parent build kit.

## ICOCR 0.8.4.8 — controller restructuring and fixes

No changes to OCR, selection, matching, tuning or the DATA format. ICDB is unchanged (0.4.2).
Extract to a new folder as usual; existing DATA, settings and logs are used as they are.

### Fixes

- **Error dialogs no longer freeze the live view.** A failed database reload, a failed
  confirmed-reading/capture save or a click-log write error opened a modal dialog
  inside the 30 Hz display loop. Video, Live tracking and OCR results stopped until
  OK was pressed. The dialog now opens after the loop has rescheduled itself, and
  identical messages are not stacked.
- **The window always closes.** An unexpected error while saving settings on exit
  stopped shutdown, and the window's close button then failed every time. Settings
  errors are now logged and reported, and closing continues. Settings → Close also
  hides the window even if saving fails.
- **Detector model path is stored resolved.** The path used to compare cached
  detections with the active model was saved in a different form from the one the
  detector worker reports. With a symlinked or `..` path, detections were hidden and
  the detection cache was never used. A saved model outside DATA/models is now
  ignored with a log entry instead of raising.
- **Snapshot preprocessing is saved atomically.** `preprocessing.json` was written
  in place without error handling. A failed write escaped the dialog and could leave
  a half-written file, which fell back to Standard on the next start. It is now
  written to a temporary file and replaced; on failure the previous settings stay
  active and a message explains why.
- **A stray click keeps the selection.** A click on the video without dragging, and
  not on a detector outline, used to reset the selection to the default centre
  region. The previous selection is now kept.
- Message boxes for opening images, choosing models and click-log errors are
  parented to the main window, so they no longer open behind it on Windows.
- Clicking a reading no longer refreshes the status twice.

### Removed (unused)

- Saved-match editing methods with no button: `lookup`, `datasheet`, `save_match`,
  and `database_details`. Known markings from `DATA/matches.json` and the bundled
  ULN2003 entry are still loaded: they rank OCR candidates and appear as
  "Saved entry" in Diagnostics.
- The snapshot archive (`snapshot_archive.py`, the `save_snapshots` switch and the
  `archive_new` request field). It had had no control since the option left the UI,
  so it never saved anything. Legacy tuple requests that still carry the flag are
  accepted and ignore it.

### Restructuring (developers)

`app.py` (2,755 lines, one class with 112 methods) is split into one mixin per
concern. `App` keeps the same public methods, so tools and tests call it as before:

| Module | Lines | Responsibility |
| --- | ---: | --- |
| `app.py` | 268 | `main()`, `App`, complete default state (`_init_state`), `invalidate` |
| `app_layout.py` | 217 | widget construction, split into toolbar/body/footer/settings tabs |
| `app_settings.py` | 270 | saved preferences, Settings actions, toggles, model selection |
| `app_database.py` | 94 | background catalogue loading |
| `app_capture.py` | 189 | camera/image input, region selection, keys |
| `app_scanning.py` | 434 | scan requests, OCR worker thread, results, verification |
| `app_live.py` | 382 | Live tracking, voting, observation, overlay motion |
| `app_readings.py` | 330 | snapshot preview, readings list, technician choice, confirmation log |
| `app_render.py` | 247 | video canvas and overlays |
| `app_diagnostics.py` | 124 | Diagnostics text (built Tk-free, inserted once) |
| `app_lifecycle.py` | 238 | tick loop, background polling, deferred dialogs, shutdown |
| `app_presenters.py` | 132 | Tk-free status, overlay-label and confirmed-row text |
| `app_helpers.py`, `app_state.py` | 249 | image/canvas helpers; DATA paths, logging, click-log migration |

- All ~140 controller attributes are created in `App._init_state()`. Settings and
  status fields start as plain values and become Tk variables in `build()`. This
  removed 129 `hasattr`/`getattr(self, …)` guards, which had also hidden mistakes such
  as misspelt attributes silently falling back to a default.
- Importing `app` no longer creates folders, configures logging or writes the log.
  `main()` does this.
- Duplicated code was merged into single helpers: the settings name lists, detector worker set-up (3 copies), capture backend,
  runtime/footer status (2), result clearing before a scan (2), list filling (2),
  `open_folder`/`open_data_folder`.
- The OCR worker loop dispatches to `read_scan` / `read_refinement` / `read_multi`, and
  `accept_results` to `accept_scan` / `accept_verification` / `accept_multi`.

## ICOCR 0.8.4.7 — UI update (with ICDB 0.4.2)

### ICDB
- Edit all selected pinout associations in one dialog. Common values are populated; mixed fields stay unchanged unless checked or typed into. Clear a checked field to clear its value.
- Double-click a device association to open the editor. If the row is already part of a multiple selection, the editor applies to that selection.
- Set default applies to every selected device in one transaction. Selecting multiple associations for the same device is rejected: only one default per device is supported.
- Unlink selected removes every selected association while retaining shared images.
- Click any table heading to toggle ascending/descending sorting. Text is case-insensitive; numeric portions sort naturally (8, 16, 100). Sort is retained when refreshing tables.
- Search supports * (zero or more characters) and ? (one character), case-insensitively. Examples: 74HC*, *240*, 74HC??. Without wildcards, search remains a substring search. % and _ are literal characters.
- All matching records are displayed and sortable; the previous 500-result truncation is removed.
- Add device accepts part number, function/description and manufacturer/group. Empty part numbers and case-insensitive duplicates for the same manufacturer are rejected.
- Delete selected devices requires confirmation with No as the default. Removes selected catalogue records, their evidence entries and pinout links. Source archives and shared image files remain. Review entries cannot be deleted through this action.
- Batch association edits are atomic: a duplicate package association or invalid pin count leaves the whole selection unchanged.

### ICOCR
- Database and Documentation are combined into Database & Documentation.
- Log clicked readings is in that Settings tab; its explanatory help paragraph is removed.
- Open image folder sits next to Capture image and opens DATA/captures, creating the folder if needed.
- Pinout refresh and index status are moved to the combined database tab.

## ICOCR 0.8.4.6

Use **Settings → Database → Choose DATA folder…**. Restart both ICOCR and ICDB
after changing it. The same selection is shared with ICDB 0.4.1.

ICOCR reads only DATA/components.sqlite and its linked DATA/pinouts images.
The package selector, shared images, default references, remembered session choices
and live reference updates remain. Images without saved ICDB associations are not
selected through filename fallback.

Removed separate database-file selection, JPEG-folder fallback and reference-bundle
selection from the interface. **Reload database** reads DATA/components.sqlite;
**Refresh pinout references** refreshes the saved associations and image metadata.

The chip-body detector uses DATA/models. **Import / select chip-body model…** opens
there and copies an external ONNX model plus its JSON sidecar into that directory.
Different existing files are not overwritten. The selected model is remembered
relative to DATA/models so moving the whole DATA folder remains portable.
The default detector searches ic_body_obb.onnx, ic_body.onnx and ic_body_segment.onnx.
Stock OCR models are initialized under DATA/models/ocr at first engine use.

ICOCR's captures, logs, settings and caches now live in the same shared DATA folder.
Dependency versions and OCR selection rules are unchanged.

## ICOCR 0.8.4.5 — ICDB pinout integration

### Connect your ICDB 0.4 database

1. Extract ICOCR 0.8.4.5 into a new folder and use the normal setup/launcher.
2. In **Settings → Database → Load database**, select the `components.sqlite`
   inside your working **ICDB 0.4** folder.
3. Leave ICDB's **pinouts** folder beside that database. Do not copy only the
   database into ICOCR: the saved references point to those image files.
4. Scan or select a recognised device. Its references appear in **Pinout / reference**.
5. Use **Package / reference**, beneath the image, to select SOIC, DIP or another
   linked image. With only one reference the field shows its label and is disabled.

No export is needed for this direct connection. ICOCR opens the database read-only.
Continue creating/editing pinout associations in ICDB. Saved link changes are
checked in the background approximately every five seconds. Image availability
is rechecked every 30 seconds. **Settings → OCR → Refresh pinout references**
requests an immediate refresh. Reloading the catalogue is only needed for changes
to catalogue contents; pinout association changes refresh independently.

### Optional reference bundle or separate database

Under **Settings → OCR**, choose **Choose ICDB database / reference bundle…** and
select either another ICDB `components.sqlite` or the `pinout_references.json`
created by ICDB's **Export references…**. Keep the exported `pinouts` folder beside
the JSON file. Re-export after editing ICDB if using this snapshot workflow.

The chosen source is remembered across restarts. **Use loaded catalogue for
references** restores the automatic connection to the active recognition database.
Loading an older ICDB database without pinout tables still works normally.

### Selection rules

- One image can serve several devices, and each device can offer several packages
  or reference images. Only explicit ICDB associations are used.
- References match the selected catalogue part number **and** manufacturer/source
  group; component IDs are not assumed to match between different databases.
- A choice made during this session takes priority when returning to that device.
  Otherwise ICOCR prefers an exact catalogue package match, then ICDB's default,
  then the first reference. The selected package is always displayed. A known
  catalogue package differing from the chosen image is stated below the image.
- The selector includes optional pin counts and labels. Images with identical
  labels have distinct choices. Choosing a reference does not identify the
  physical package automatically or change the OCR result.
- ICDB references take precedence over folder-discovered JPEGs for that device.
  If ICDB has no linked reference for the part, the existing folder and explicit
  aliases remain available. A manufacturer mismatch does not use another
  manufacturer's ICDB image. Missing managed images remain selectable and show
  an error instead of silently substituting a folder image.
- Existing automatic JPEG folder discovery remains active. Its package variants
  are also selectable. Duplicate device/package filenames require a selection.
- JPG, PNG, BMP and WebP are supported for ICDB-managed references, up to 24 MP.
  Automatic legacy folder discovery continues to accept JPG/JPEG.

The centred image, white border, click-to-enlarge, fixed recognition-status area,
and retention of the last accepted reference through temporary OCR dropouts remain.
The reference panel still applies to single-chip mode.

## ICOCR 0.8.4.4 — Scan verification and responsive references

- Added Settings > OCR > Scan verification, enabled by default and saved with UI preferences.
- Live single-chip verification revisits the current OCR input region, including all detected marking lines. Uses the existing OCR worker; no parallel inference queue.
- Accepted unambiguous exact/verified-alias matches are left alone. Unmatched, partial or ambiguous selections can receive up to three verification scans, spaced at least 1.2 seconds between starts, while the same target remains tracked.
- Verification bypasses orientation early acceptance, the optional reverse-reading classifier gate, and incumbent selection preference. Normal body/input-region settings still apply.
- Promotion requires the same unambiguous exact/verified-alias identity in two distinct verification frames. Empty, weaker, single conflicting, cancelled and failed checks preserve existing rows, tracking and reference. Manual selections are respected.
- Checks stop when disabled, and pending checks cannot promote after disabling, changing the scene, losing the target or making a manual selection. Existing normal acquisition/retry behaviour remains available.
- Diagnostics/log entries record verification candidates, attempts and acceptance decisions.
- Reference panel is outside the scrolling controls, anchored at the bottom of the right section. Its image expands and shrinks with available width/height, preserving aspect ratio, an eight-pixel white border and click-to-enlarge.

### Scope

This release targets missed matches. It does not routinely challenge accepted exact matches. No live multi-chip verification is added. Verification cannot recover text outside the configured OCR input region.

## ICOCR 0.8.4.3 — Reliability and performance

Extract into a new folder as usual. **Copy `diagrams/` and `models/` from your 0.8.4.2 folder**
(the supplied 0.8.4.2 archive did not contain them, so they are not in this package either).
User data in `%LOCALAPPDATA%\ICLens` is unchanged; no migration is needed.

### Fixes

- **No more silent freezes.** An error in the display loop used to stop video, results and polling until restart. It is now logged once to `ic_lens.log` (repeats are counted), shown in the status line, and the loop continues.
- **Bounded, clean shutdown.** All background workers share a 5 s close budget. The camera thread is joined so the device is released (avoids a locked camera on the next start). Anything still running is logged and the window closes anyway.
- **Sources line** no longer crashes on a database record with a missing/NULL source name.
- **Database details** has the same bounds check as the other list actions.
- **Min/max tuning pairs** (`*_min` / `*_max`, e.g. neighbour heights, tracker scale): a max below its min is now rejected, both are restored to defaults and a startup warning is shown. Previously this silently disabled neighbour, fragment and wrapped-line detection.
- **Ranking** reads `component_catalog.pending_database_score` instead of a hard-coded 0.60, so retuning it is consistent everywhere.
- **Detector model discovery** now also finds `models/ic_body_segment.onnx`, the model the manifest lists.
- **Configured preprocessing** now has the same CUDA→CPU fallback as the standard path.
- **Empty/missing frames** raise a clear error instead of an obscure OpenCV crash; ROIs are clamped to at least 1 px. `gpu_check` reports a missing image file properly.
- Camera-list failure no longer re-enumerates on the UI thread; it falls back to device indices 0–5.
- An invalid `ICLENS_DEVICE` value falls back to `auto` with a warning.
- Only one Snapshot preprocessing window can be open; a malformed policy file shows a clear error.

### Performance

- Snapshot preview is downscaled first, then preprocessed (Illumination ≈389 → 57 ms, Local contrast ≈92 → 24 ms on a 3000×1700 crop). Previews may differ very slightly, mostly with Sharpen/Threshold.
- Per-scan configuration diagnostics (deep copy + two hashes on every scan) are computed once at start-up.
- Live mode: one grey conversion per frame for all trackers; the overlay caches the previous frame's thumbnail/features; Observation Live no longer copies the ROI every tick; unchanged status text and canvas items are not re-set every tick; camera FPS is read once.
- Motion gate signature is made in two steps (linear to 640 px, then area average), so sensor noise on a still 4K view no longer defeats detector-cache reuse.
- ONNX Runtime threads no longer busy-wait between runs, and are capped at CPU count − 2 (leaves room for tracking and UI). On a 2-core PC OCR now uses 1 thread.
- Click logging is written by a background writer instead of `fsync` on the UI thread; pending rows are flushed on close. A write failure is still reported, a moment after the click.
- Diagram folder: idle rescans every 30 s (5 s after a change), full walk at least every 60 s, only when folder timestamps change. **Refresh diagram index** is still immediate.
- Component database alias index is cached in `%LOCALAPPDATA%\ICLens\catalog_index\` and reused when the database file is unchanged (safe to delete).
- Smaller items: snapshot copies, diagnostics deep copies, candidate selection, detector input tensor, segmentation masks, origin-exclusion and match lookups are each computed once.

### Optional OCR speed switches (off by default)

Added to `config/tuning.json`; see the 0.8.4.3 section of [config/TUNING_REFERENCE.md](config/TUNING_REFERENCE.md).
Measured on 26 inputs per scan mode (2 real board photos, 24 rendered markings at 0/90/180/270°, blur/noise):

| Setting | Effect | Same selected text | Default |
|---|---|---|---|
| `ocr_core.full_shared_detection = 1` | Full scan: 2 detection passes instead of 4, angle classifier off. **Correct rotation labels** (24/24 vs 8/24) | 25/26 | off |
| `ocr_core.cls_gate_enabled = 1` | Fast scan: skip the 180° re-read when the classifier is confident | 26/26, but ~6% slower on CPU | off |
| `ocr_runtime.det_limit_side_len = 960` | Caps detector resolution | 25/26 | off (0) |

Measured speed-ups: shared detection about −56% full-scan time; detector limit 960 about −55% fast and −63% full. Because they changed a selection on the test set, they are not on by default. **Recommendation:** try `full_shared_detection = 1` and `det_limit_side_len = 960` on your own chips and compare.

One fixed change affects selections: OCR probes larger than the limit are now shrunk with area averaging (sharper thin strokes). In testing it changed one result: a whole 4K board selected as one region read `A240K1491` (0.99) instead of `ISN024` (0.84).

### Code structure

- Scan requests and results are typed messages (`scan_messages.py`) instead of 9-field tuples.
- Duplicated canvas pooling and display text code consolidated; dead code removed.

### Development and release hygiene

- Python 3.10–3.12 is required (3.13 is not supported by the pinned OCR packages).
- On Linux/macOS user data moves from `~/ICLens` to `~/.local/share/ICLens`; `ICLENS_DATA` overrides it on every platform. Windows is unchanged.

## ICOCR 0.8.4.2 — Automatic JPEG diagram library

### Use

Open **Settings → OCR → Choose JPEG diagram folder…**. The selected folder is saved in your existing user settings, independently of the application installation. Files remain in that folder; ICOCR does not move, recompress or modify them. Subfolders are included. **Use default diagram folder** restores the configured default.

Add files using these names:

| Name | Selection |
| --- | --- |
| `74HC08.jpg` | General reference for 74HC08; package unspecified |
| `74HC08__SOIC14.jpg` | 74HC08 with a known SOIC14 package |
| `74HC08__TSSOP14.jpeg` | 74HC08 with a known TSSOP14 package |

Names and extensions are case-insensitive. Separate device and package with two underscores. Package spaces, hyphens and underscores are ignored for comparison: SOIC-14 equals SOIC14. Other package synonyms are not guessed. The package comes from the selected database record, not an inferred visual package. Unknown/mismatched packages cannot select a package-specific reference. A general file remains available as an explicitly package-unspecified reference.

The accepted database part number must match the filename. Existing explicit starter aliases for HC00/08/32/86 and compatible old JSON mappings are retained. Arbitrary manufacturer prefixes or suffixes are not stripped, and different logic families are not substituted. For other aliases, provide a filename matching the resolved database part.

New files need no JSON entries. `config/logic_diagrams.json` now contains general defaults and an empty optional legacy mapping section. Previously customized files remain supported. New JPEGs are labelled **User-added reference**; filenames do not establish pinout verification, source or orientation.

### Discovery and storage

- A background worker scans the folder at startup and every five seconds after the preceding scan finishes. **Refresh diagram index** requests an earlier scan. Larger or network folders can take longer.
- Changed/new files receive JPEG header and dimension checks; unchanged files reuse persistent metadata. No image pixels are decoded during indexing. Files above 24 megapixels, unsupported names, symlinks and invalid JPEG headers are skipped. A corrupt image body is reported if loading fails.
- The SQLite index is stored under the existing user-data directory: `%LOCALAPPDATA%\ICLens\diagram_index` on Windows. Each folder has a separate index. The JPEG folder does not need write access. The index is disposable; deleting it while ICOCR is closed causes a rebuild.
- Recognition-time lookups use an in-memory index. No directory scan or full-library image loading occurs during lookup. Only the displayed image is decoded, and it is reused until the file/device changes. Click-to-enlarge, centered layout, white border and fixed-height recognition status are preserved.
- Additions, changes and deletions update the displayed reference after discovery. Duplicate device/package keys are blocked and counted in Settings. Missing/inaccessible folders disable references with an index status message; scanning/OCR continues.

### Scope

JPEG only. No packed distribution, image transcoding, OCR-rule changes or ICBENCH work. ICBENCH remains paused at 0.5.3 and is not included.

Extract into a new folder and use the existing launcher. The prior release's configuration and recognition improvements remain.

## ICOCR 0.8.4.1

- Centered logic images horizontally and vertically in a fixed-height white viewport. Aspect ratio is preserved, with an eight-pixel white border. The original image remains available through click-to-enlarge.
- Fixed-height status section below Recognised markings. Device, function, scan/match state and essential warnings use bounded lines; long values are ellipsized using the current font metrics.
- Removed status tips and repeated explanations. Full candidate evidence, sources and scan errors remain in Settings → Tools → Diagnostics.
- Removed the accidentally bundled ICBENCH directory and related 0.8.4 integration claims. ICBENCH remains paused at 0.5.3. This release contains no benchmark update and does not modify a separate ICBENCH installation.
- Preserved external configuration, recognition rules, models and diagram mappings from 0.8.4.

Extract into a new folder and run the existing Windows setup/launcher. Do not merge into 0.8.4, because merging retains its old ICBENCH directory. Existing customized configuration can be copied as described in the 0.8.4 release notes.

## ICOCR 0.8.4

### What changed

- Validated external numeric tuning for selection, candidate scoring, bounded affix matching, scan scheduling, optical tracking and frame voting. `config/tuning.json` keeps the previous numeric defaults.
- Configurable HC/HCT abbreviations (`HC08`, `HC240`, `HCT08`, `HCT240`) resolve only to an existing unambiguous `74` base. Raw OCR remains separate. Exact matches win; families are never substituted. Manufacturer and package remain unresolved.
- Explicit family suffix rules, including `74HCT273D` → `74HCT273`, record the applied rule. The existing general literal-suffix policy remains available as before.
- A single **Settings → OCR → OCR input region** dropdown replaces the two crop checkboxes. **Show live chip detections** remains independent. The selected/default model filename is shown beside **Choose chip-body model…**.
- Snapshot status reports full selection, geometric body or model body. Model-unavailable → geometric fallback and failed-body → full-selection retry are reported with reasons. Recognition fallback behaviour is preserved.
- **Show logic diagrams** adds a clickable reference below the recognised-reading details in the right sidebar. It is enabled by default and saved in settings. It uses accepted matches only, holds the last accepted reference through brief OCR dropouts with a visible label, and clears on scene/control changes. Single-chip mode only.
- Starter original JPG references: **74HC00 (NAND), 74HC08 (AND), 74HC32 (OR), 74HC86 (XOR)**. Each shows internal logic, pin assignments and top-view orientation. Explicit 14-pin mappings include base/SN-prefixed names and D/N/PW forms. Other devices/families show **Logic diagram unavailable**. Sharing an image does not imply electrical interchangeability.

### Upgrade

Extract into a new folder and use the normal Windows launcher. Existing application data and saved crop settings are read from the same location. All four legacy checkbox combinations migrate without changing their crop method; unrelated UI preferences survive saving.

If you customized the old `config/` files, copy those customized files into this release (or point `ICOCR_CONFIG_DIR` at your existing directory). Missing new settings/files receive bundled defaults in memory. Valid user values are retained; malformed values are reported. No configuration file is automatically overwritten. Run `run_windows.bat config-check` after edits.

The configuration set is version 2; existing file schemas remain version 1. Unknown future file versions use defaults with a warning.

The only intended default recognition extension is the requested abbreviation support. Numeric thresholds and crop/retry decisions retain 0.8.3.9 values. To compare legacy selection, set `abbreviations` to `false` in `rules/marking_aliases.json` (suffix labelling still supplies provenance for an existing match).

### Models and diagrams

The uploaded `ic_body_segment.onnx` and its JSON are retained unchanged. Choose this file explicitly in **Choose chip-body model…** if it is your intended model. Existing default model lookup order is preserved; the filename label reports that default if no custom model is selected.

Add verified JPGs under `diagrams/` and explicit entries to `config/logic_diagrams.json`. Do not add wildcards or assume that suffixes/families share pinouts. Each mapping requires a source, package description, `top view` orientation and `verified: true`. Missing/corrupt images do not interrupt scanning.

## ICOCR 0.8.3.9 — external marking configuration

### Scope

First configuration extraction from the supplied 0.8.3.8 source. Editable JSON
lives in `config/` beside the application. Defaults preserve existing behaviour.

- `rules/part_prefixes.json`: literal part-number prefixes.
- `rules/negative_words.json`: origin words/phrases and additional exact exclusions.
- `rules/device_families.json`: syntax rules, display hints, allowed whitespace
  joins, orientation syntax thresholds and context-specific correction costs.
- `rules/ocr_confusions.json`: bidirectional pairs, costs, suffix conversions and
  bounded automatic-correction limits.
- `rules/brands.json`: existing printed brand/logo words.
- `ranking/line_weights.json`: existing fitted weights and metadata, ranking
  enable flag, abstention threshold and extended-pool score.

Read `config/README.md` for fields, bounds, examples and upgrade handling.

### Runtime behaviour

Configuration is loaded and validated at startup. Restart to apply edits.
Lists replace defaults. Missing/invalid files use bundled defaults per file and
show a startup warning. Errors name the file and field. The loader never writes
or repairs configuration files. Configuration fingerprints and fallback status
are included in OCR diagnostics and serialized scan results.

Confusion lookup groups are derived from listed pairs. Pair membership is still
checked on every candidate substitution; a connected group does not allow
unlisted substitutions. Raw OCR, database uniqueness requirements and existing
selection protections remain intact. The default 74HCT T correction is preserved.

The ranking fitter writes validated output atomically to the new ranking path.
The previous per-call brand/weight file timestamp checks are removed. The existing
`ICOCR_LINE_RANKING` override remains available and is included in diagnostics.

Validate without loading OCR models:

```bat
run_windows.bat config-check
```

Or use `python manage.py config-check --json`. Exit 0 means all files loaded;
exit 1 means at least one fallback is active.

### Installation and migration

Extract to a new folder and use the existing setup/launcher procedure. No new
Python dependency is introduced. The shipped older root-level brand/weight files
have been migrated and removed from the root to avoid competing configuration
sources. Separately customized copies must have their values transferred to the
new schema as described in `config/README.md`.

Preferences, logs, snapshots and remembered database paths remain in their
existing AppData location. Camera, preprocessing, detector, live tracking and
other operational settings are deferred. ICBENCH is not modified. Installer/EXE
work and relocation to writable user directories are deferred.

## ICOCR 0.8.3.8 — Log only confirmed readings

Full package (0.8.3.7 plus this change). No new dependencies.

### What changed

The old Logging wrote an encounter record for every scan (crop PNG, context
JPEG, record.json), tried to tell chips apart by scene changes and needed
New IC for look-alike replacements. It is replaced by something simpler:

**A reading is logged only when the technician clicks it** (or corrects it
with Edit reading). The click is the confirmation that the text is right.

Each confirmation saves, in `%LOCALAPPDATA%\ICLens\confirmed`:

- `C_000001.jpg`, `C_000002.jpg`, …: the scan snapshot, JPEG quality 95, no
  overlays. Normal scan: the selection. Multi-chip: that chip's region.
- one row in `confirmed.csv`:

```
time,image,part_number,confirmed_text,database_match,corrected,correction,ocr_text,automatic_pick,all_readings,mode,chip,scan,database
2026-10-06 13:42:04,C_000001.jpg,JA1044V,JA1044V,no,no,accepted automatic pick,JA1044V,JA1044V,JA1044V | TN237 | NXP | 0203AH,scan,,…
2026-10-06 13:42:04,C_000002.jpg,0203AH,0203AH,no,yes,picked another line,0203AH,JA1044V,JA1044V | TN237 | NXP | 0203AH,scan,,…
```

- `part_number`: the database part when the reading matched, else the text.
- `corrected`: **no** when the ★ automatic pick was clicked; **yes** when the
  technician picked another line or edited the text (`correction` says which).
- `ocr_text`, `automatic_pick`, `all_readings`: what the OCR saw. With
  `corrected` these are exactly the examples needed to train better line
  selection later.
- `scan`: several clicks on one scan give several rows; the last one counts.
  The same reading is saved only once per scan.

### Controls

- The **Logging** checkbox is now **Log clicked readings**: on by default and
  remembered between sessions (nothing is saved without a click).
- Removed: New IC / Ctrl+N and Export scan log CSV (the CSV is the log now).
  Settings → Documentation has **Open confirmed folder**.
- Multi-chip scans can now be logged: click a chip's reading.
- Space capture is unchanged. Session-history clicks are not logged (their
  snapshot may belong to an earlier scan).

If `confirmed.csv` is open in Excel, Windows locks it: the JPEG is saved, the
row is not, and the status bar says so. Close Excel before clicking on.

Old `scan_logs` folders are left untouched; nothing new is written there.

## ICOCR 0.8.3.7 — Multi-chip scan (experimental)

Full package (0.8.3.6 plus this change). Extract into a new folder, or copy
over an 0.8.3.6 folder. No new dependencies. One new
setting, **off by default**: with it off, scanning, Live recognition and Logging
behave exactly as in 0.8.3.6 (only additions were made to `app.py`).

### Use

1. Settings → Recognition → tick **Multi-chip scan (experimental): read every
   chip in the selection**. The setting is saved like the others.
2. Drag a selection around the chips you want (or the whole view).
3. Press **Enter** or **Scan**.

Each chip gets a numbered marking outline and a label on the video (green: exact
database match, amber: other, grey: unconfirmed), a dashed body outline when a
body was found, and one line in Recognised markings:

    Chip 1: ★ 93LC46B
    Chip 2: ★ A240K1491
    Chip 3:   538BCP (unconfirmed)

★ automatic pick, ✓ technician choice. Clicking a line searches it and records
the click, as before. **Edit reading** corrects the selected chip. The frozen
snapshot preview shows the numbered markings too.

### How it works (`multi_chip.py`)

1. **Find text.** One fast OCR pass (0°/90° detection, every line read both
   ways) over the selection. Only if part-like text comes out very small is the
   selection read again in overlapping tiles at higher resolution.
2. **Group lines into chips.** Lines of similar character height and direction
   that sit within about a line height of each other form one marking block. A
   block becomes a chip only if it has a part-like line: letters and digits,
   4+ characters, OCR score ≥ 0.60, not a reference designator. Resistor codes
   (472, 4701), board labels (R45, IC3, XTAL) and logos alone never make a chip.
3. **Detector bodies.** With *Body from chip detector* on, each detector body
   lying fully inside the selection becomes a chip; text blocks on a body join it.
4. **Read each chip** with the unchanged single-chip pipeline
   (`body_scan.read_with_body`) and your current settings: fast scan, auto body
   crop, detector body, Targeted Original, snapshot preprocessing, database. The
   region around a chip is its marking plus room for the body; text belonging
   to the other chips inside that region is painted over first, so a neighbour's
   marking cannot become this chip's reading.
5. If the selection rules make no automatic pick (e.g. a chip cut by the frame
   edge), the best part-like reading is shown grey as *unconfirmed*.

Overlays follow camera movement with the existing motion worker and hide when
the view changes too much. A new selection, a setting change or a new image
clears them. At most 10 chips are read per scan (strongest markings first).

### Limits

- **Manual scans only.** Live recognition is paused while the option is on
  (the status bar says so). Live tracking/voting is still one chip.
- **Not logged.** Logging records single-chip encounters; multi-chip scans are
  not written to the scan log (the status bar says so when Logging is on).
- **Any part-like printed text is a chip** — inductors, modules and large
  connectors with codes appear too. A chip with no readable marking is not
  found unless the trained detector finds its body.
- **Time grows with the chip count**: discovery plus one normal scan per chip.
- Readings are evidence, not identity, exactly as for single scans.

### Results on the two supplied images (CPU, no database, default settings)

Measured in a 2-core cloud sandbox; expect shorter times on a desktop CPU and
much shorter on CUDA.

| Image | Chips | Readings | Time |
|---|---|---|---|
| Two NXP CAN transceivers, 1600×843 | 4 | JA1044V ★, JA1044V ★ (each its own chip, body crop applied); M234622 ×2 provisional (the inductors) | 6.5–7.4 s (discovery 1.5 s) |
| Dense board, 3840×2160 | 3 | 93LC46B ★; A240K1491 ★ on the DEI448T chip; 538BCP unconfirmed (chip cut by the frame edge) | 9–11 s (discovery 1.4 s) |

On the dense board the large chip's part line is read as "DEI48T" (one 4
missing), so without a database the selection rules prefer the lot code
A240K1491 — the same pick a single-chip scan of that chip makes. The ULN driver
and the 2903 chip are cut by the image edge with too little of their marking to
count as chips.

### Rollback

Untick the setting. For a full code rollback, restore `app.py` and `version.py`
from 0.8.3.6; `multi_chip.py` is then unused and can be deleted.

## ICOCR 0.8.3.6 — Observation Live prototype

This optional live scheduler tests whether tracking and selective line rereads can reduce repeated text detection. It is disabled by default. Install over ICOCR 0.8.3.5 only.

### Behavior
- Sample image quality at most 20 times per second; retain a sharp recent view and its matching tracking geometry.
- Acquire through the native detector/body pipeline. Skip live treatment retries, straighten fallback and body recovery in prototype acquisitions.
- Once a marking is tracked, reread only that line in the known direction. Do not repeatedly run full detection on the same tracked target.
- Count exact text observations from distinct captured frames. No initial seed vote and no constructed character consensus. Confirmation uses the existing minimum of three votes with confidence >= 0.85 and share >= 0.75.
- After three reads, require a 25% quality improvement for further line reads; cap at six. An unchanged scene allows at most two acquisitions, with the second requiring improved quality and changed visual evidence.
- On a stable result, track without OCR. Persistent marking changes or tracking loss permit reacquisition. Unresolved results wait for better evidence instead of endlessly retrying the same view.
- Preserve unknown/provisional identity: stable text does not create a database match.

### Camera trial
Check Performance/Diagnostics for the observation state, full-scan count, line-read count, quality and stable flag. Counters describe the current observation, not lifetime totals.

Hold a clear known chip still: acquisition should lead to line reads, then tracking only. Hold an unknown chip still: a stable raw marking may rest without database identification. Defocus or add glare: it should wait; refocus to provide better evidence. Swap chips and move the target out of view: the old result should invalidate and the new target should be acquired. Compare time to a *correct* stable result, wrong stable results, unresolved results and detector counts with the checkbox off/on.

The quality and appearance thresholds are experimental. Distinct frames are not independent evidence: repeated OCR errors can still become stable. The appearance heuristic can miss subtle chip swaps. One tracked marking is handled at a time. Removing retries may increase abstention or miss text that needs another orientation or preprocessing. The bounded request counts are not a timeout for an individual model inference.

### Rollback
Disable Observation Live to return to the normal live scheduler. For complete code rollback, close ICOCR and copy the four files inside rollback_0_8_3_5/ into the application folder, replacing their prototype versions. The new live_observation.py and tests/test_observation_live.py can then be removed. Do not move the rollback folder itself into the root as a replacement for those files.

## ICOCR 0.8.3.5 — Space capture, database-guided correction, joins, body check

Drop-in update for an ICOCR 0.8.3 folder; includes 0.8.3.1-0.8.3.4. Copy the
files over the folder and replace when asked. No new dependencies or settings.

### Keys and captures

- **Space** saves the full current frame (Capture image). One image per key
  press: holding Space does not repeat. If the save queue (4 images) is full,
  the status bar says so; no dialog.
- **Enter** starts a scan (Space did this before). Both keys are ignored while
  typing in a text field or list control. Buttons: "Scan [Enter]",
  "Capture image [Space]".
- **Captures are JPEG quality 95** (`IC_000124.jpg`, about 2 MB instead of
  15 MB at 4K). Numbering continues after existing PNG captures; no file is
  overwritten. The scan log's OCR crop stays lossless PNG; its context image
  was already JPEG.

### Database-guided character correction

A reading without its own database match is checked against the database with
up to 1 substitution (under 6 characters), 2 (6-8) or 3 (9+), using only listed
OCR confusions: 0/O, 0/D, D/O, 0/Q, O/Q, 1/I, 1/L, I/L, 1/T, I/T, 5/S, 8/B, 2/Z,
6/G, M/N, U/V/W. It becomes the match only when exactly one database part is
reachable, the total substitution cost is bounded and OCR scored at least 0.85
(0.90 before). A digit misread in a package suffix may resolve a literally
printed base (74HC1630 → 74HC163). The raw reading is never rewritten; the
list shows "corrected from …" and Diagnostics lists each substitution.

Still not corrected: two reachable parts, reverse readings, missing characters
(no completion: MCS6F does not become MC56F8006), low OCR scores (M29WB00FB at
0.78), and unlisted pairs in the same character class (2903D is not changed to
2903Q).

### Joined line fragments and logo letters

- **Fragments of one printed line** read as separate boxes (same direction and
  baseline, next to each other or overlapping by re-read characters) are joined
  when the result has trusted database support: TLE723 + 38SL → TLE7238SL.
- **Logo letters** read in front of a code (MNCV7356G) are dropped when the
  rest has trusted database support and the reading itself has none:
  NCV7356G → NCV7356.

The original readings stay listed; derived ones are marked in the list and in
Diagnostics.

### Body-crop size check

A geometric body outline covering less than 6% of the selection (a pin-1 mark,
glare or a text-free patch) is not used: the full selection is scanned directly
instead of reading the crop and then recovering. On the 78-image benchmark this
affected two images (2.4% of the selection, no text inside); every useful body
covered at least 8.7%. Bodies from the trained chip detector are not affected.
`ICOCR_BODY_MIN_FRACTION=0` disables the check.

### Results

Replay of the recorded readings of both ICBENCH runs with the real component
database (15,062 names):

| | 0.8.3.4 | 0.8.3.5 |
|---|---|---|
| Run 20261005_110453 (119 IC): primary selected | 65 | **69** |
| — database identity correct | 31 | **35** |
| — non-IC images with a selection | 3/14 | 3/14 |
| Run 20261005_065203 (74 IC): primary selected | 47 | **49** |
| — database identity correct | 23 | **26** |
| Previously correct, now wrong | — | 0 |

Gains: DS1307 (0S1307), ATSAM9G45 (AISAM9G45), 74HC163 (74HC1630, identity),
BTB06-600BW (BTB06-600BU), TLE7238SL (joined), NCV7356 (MNCV7356G). Across all
readings of both runs no lot code or non-IC text was corrected, joined or
stripped into a database part.

Real OCR on the 78 images of the first run (CPU, geometric body crop, real
database), back to back on the same machine:

| | 0.8.3.4 | 0.8.3.5 |
|---|---|---|
| Primary selected | 51/74 | **53/74** (DS1307, ATSAM9G45; none lost) |
| Database identity changes | — | +3 (DS1307, ATSAM9G45, 74HC163) |
| Non-IC images with a selection | 1/4 | 1/4 |
| Mean OCR passes / median / 95th percentile | 3.00 / 1.12 s / 5.7 s | 2.90 / 1.09 s / 5.6 s |
| Body-crop recoveries | 12 | 10 |

The line-ranking refit with the real database gave the same weights as 0.8.3.4
(cross-validated 70/119 vs 69 for the rules; 31 wrong and 3 non-IC picks each).

### Changed tests

Earlier tests that refused these corrections were updated deliberately:
two substitutions (ULN2OO3), the 0.85 OCR gate (LM3S8N at 0.89, 0S1307 at
0.893), no family-pattern requirement (XYZ12B), and the corrected package
suffix (74HC1630 → 74HC163). Their protective cases remain or were extended
(three edits in seven characters, low scores, reverse readings, two reachable
parts, 0/D inside a base with a suffix). Three conflict tests now use a
non-confusable character, because the old example spellings resolve to the
same part. The capture tests expect JPEG.

## ICOCR 0.8.3.4 — recognised-markings failsafe, faster retries, tilt fallback

Drop-in update for an ICOCR 0.8.3 folder; includes 0.8.3.1-0.8.3.3. Copy the
files over the folder and replace when asked. No new dependencies or settings.

### Recognised markings: always a choice

The automatic pick is a convenience, not a gate. The list now always shows every
usable reading, so the technician can pick the correct or closest one:

1. **★ automatic pick** (or the reading being checked), first.
2. Readings with database support.
3. Every other reading, best line score first; text outside the marking block
   and reverse readings last (grey).
4. Whole printed lines whose text differs from their tokens (e.g. `I/P e3 RUG`).
5. With **Show all recognised text**: PCB references, origin text, short values.
6. If nothing qualified, the raw OCR lines themselves.

Previously a database match hid all other readings, and readings that failed the
selection rules were only listed with Show all.

**Clicking a reading** still logs the click and opens the web search, and it now
also makes that reading the **✓ technician choice**. The status bar shows it,
it is added to session history, and with Logging on it is saved to the scan log
(mode `technician`; the CSV export uses it). The choice stays at the top through
later live updates until the scene, selection or a setting changes.

**Edit reading…** (button under the list) corrects a near-miss reading (for
example AISAM9G45 → ATSAM9G45). The corrected text is looked up in the
database, searched, logged and used as the technician choice.

On ICBENCH run 20261005_110453 (119 IC images, recorded results): the list shows
the correct marking for 86 images (0.8.3.3: 81); in 84 of them it is first or
second. Another 13 show a reading 1-2 characters off that Edit reading can fix.
The auto pick is correct for 67.

### Fewer duplicate OCR passes with body crop

When the body-crop pass selects nothing, the full-selection recovery follows with
its own retry, so the crop pass no longer runs its own no-selection retry
(8 OCR passes → 6 in that case). `ICOCR_DEFER_BODY_RETRY=0` restores 0.8.3.3.

### Straightened read for tilted text

Fast scan never deskewed. When nothing is selected after the normal retry and
the detected lines lean 8-43°, the crop is straightened and read once more;
readings are merged and mapped back to the original coordinates. Diagnostics
records `straightened_fallback`. `ICOCR_STRAIGHTEN_FALLBACK=0` disables it.

Measured together (real OCR on the 74 IC + 4 non-IC images of the first
benchmark, CPU, geometric body crop, no database):

| | 0.8.3.3 | 0.8.3.4 |
|---|---|---|
| Primary marking selected | 47/74 | 49/74 (AHC08, HC32 gained; none lost) |
| Non-IC images with a selection | 1/4 | 1/4 |
| Mean OCR passes per image | 3.12 | 3.01 |
| Median / 95th percentile time | 1.15 s / 4.8 s | 1.08 s / 5.3 s |

The straightened read adds passes to some of the slowest, unresolved images,
so the 95th percentile rose while the median fell.

### Repeated characters

Strings of one repeated character (2222222, 0000, AAAA) are never auto-selected
(they remain listed with Show all).

### Line ranking refitted (133 images)

`line_weights.json` is refitted on ICBENCH run 20261005_110453. New hard rule: a
bare number (date/lot code, at most a database suggestion) never outranks the
rules' choice when that choice is a strong part-like marking or a family pattern
(e.g. 1841 vs NTP7515D). The fitting tool applies the same rule, and its defaults
reproduce the shipped weights (`--l2 0.03 --wrong-cost 3`).

Cross-validated on unseen chips (recorded readings, database names visible in
the run): 66/119 correct, 34 wrong, 3 picks on non-IC images; the 0.8.3.2 rule
order gives 65, 34 and 3. Training fit: 65/119. The gain is small; the main limit
is still reading (the correct line was selectable in 76 of 119 images).

### Annotation suggestions

`annotation_suggestions_v0_6.csv` (delivered separately) lists suggested
`base_partnumber` values where the database returns the base part and the
annotation adds a 1-3 letter suffix (74HC14 / 74HC14D, ULN2003 / ULN2003A, …),
and fields with stray spaces. Review before applying.

## ICOCR 0.8.3.3 — line ranking for multi-line markings

Drop-in update for an ICOCR 0.8.3 folder; includes 0.8.3.1 and 0.8.3.2. Copy the
files over the folder and replace when asked. No new dependencies or settings.
Set `ICOCR_LINE_RANKING=0` before starting to use the 0.8.3.2 selection order
(for comparison in ICBENCH: `set "ICOCR_LINE_RANKING=0"`).

### What it does

Every candidate line is scored on several kinds of evidence instead of a fixed
order of rules (`line_ranking.py`):

1. **Marking block.** Recognised text is grouped into the printed lines of one
   marking block and numbered top to bottom in the text's own reading direction
   (rotated chips included; a reverse reading stays in its line). Text in another
   direction, or far from the block (board labels), is marked as outside it.
2. **Measurements per line** (`FEATURES` in line_ranking.py): position (first,
   second or later line carrying digits; directly below a logo/brand line;
   outside the block), character height relative to the block, text shape (part
   number shape, stem+suffix, family pattern, lot shape, YYWW date prefix, only
   digits, one-letter code, length), database evidence (exact, base+suffix,
   suggestion, correction), OCR score and treatments, body/block number, and the
   0.8.3.2 rules' own choice.
3. **Fitted score.** A weighted sum with weights fitted on annotated images
   (`line_weights.json`). Fitting starts from convention-based weights
   (`PRIOR` in line_ranking.py) and is regularised towards them, so a small
   dataset adjusts rather than replaces them.

Kept as hard rules: origin text, PCB references, short resistor values,
unresolved conflicting spellings, unsupported reverse readings, withheld numeric
fallbacks, and database priority (trusted database evidence still wins; while
database evidence is pending only rows carrying it are considered).

New candidates (text the 0.8.3.2 rules never offered) must sit in a multi-line
block, contain a digit, have 3+ characters and OCR score >= 0.85, and score
above the fitted threshold (`abstain_below`). The threshold never withholds the
0.8.3.2 rules' own choice.

Diagnostics shows the block line count, and for every candidate its line score
and the largest contributing terms.

### Brand words

`marking_brands.json` lists brand/logo words (Infineon, NXP, Microchip, Sipex,
Etrontech, …). A line made of these or of letters only counts as a logo line.
Edit freely. Words under three characters (TI, ST, ON) never reach selection.

### Refitting

```bat
run_windows.bat fit-ranking --predictions <run>\predictions.jsonl ^
    --annotations <annotations.csv> --database <components.sqlite> --write
```

Quote paths containing spaces, e.g. `--annotations "annotations_v0_5 .csv"`.

Repeat `--predictions`/`--annotations` to combine runs or datasets. The report
shows the 0.8.3.2 rule result, a cross-validated result (images of the same
marking are kept in the same fold, so it measures unseen chips), the training
fit and the weights. Without `--write` nothing is changed. `--wrong-cost` sets how
much worse a wrong pick is than no pick (default 0.5).

### Results on ICBENCH 0.5.2 run 20261005_065203 (78 images)

Replay of the run's recorded OCR observations; database = names recorded in the
run's diagnostics (78), not the full ICDB database.

| | 0.8.3 | 0.8.3.2 rules | 0.8.3.3 |
|---|---|---|---|
| Primary marking selected | 45/74 | 47/74 | 48/74 |
| Non-IC images with a selection | 1/4 | 1/4 | 1/4 |
| Correct before, wrong now | — | 0 | 0 |
| Cross-validated (unseen chips) | — | — | 47/74 |

**The main limit is reading, not ranking.** The correct line was among the
selectable readings in only 51 of 74 images, and the 0.8.3.2 rules already chose
it in 47 of those. The other 23 were not read correctly (faint marking, glare,
tilt, single-character misreads) or were unresolved conflicting spellings.
Cross-validated, the fitted model equals the rules; with 51 usable training
images it cannot yet show a reliable gain beyond them. Refit as annotated images
are added: each fold's estimate becomes more trustworthy with a few hundred.

## ICOCR 0.8.3.2 — responsiveness and resource fixes

Drop-in update for an ICOCR 0.8.3 folder. It includes the 0.8.3.1 selection
changes (0.8.3.1), so it can be applied over 0.8.3 or 0.8.3.1. Copy the
files over the folder and replace when asked. No new dependencies or settings.
OCR recognition, selection and matching are unchanged from 0.8.3.1.

### Changes

| | Change | Effect |
|---|---|---|
| A | Preview downscale: an integer-factor INTER_AREA step, then INTER_LINEAR (`preview_resize` in app.py) | About 13 ms → 2 ms per 4K frame on the window thread; display only |
| B | The preview reuses one Tk image (`PhotoImage.paste`) while the canvas size is unchanged | About 1-2 ms less per frame |
| D | Load database / Reload / startup database read the catalogue on a worker thread | No frozen window while a large database is indexed. The previous database stays active until the new one is ready; a failed load keeps it and reports the error |
| E | Overlay motion history holds weak references to frames | Up to eight full frames (~200 MB at 4K) are no longer kept alive; overlay geometry is unchanged |
| G | Log context image (`scan_logs/<IC>/context.jpg`) is a quality-95 JPEG | About 7× smaller (≈15 MB → ≈2 MB at 4K) and ≈18× faster to write. `crop.png` (OCR input) stays lossless; **Capture image** is unchanged (lossless PNG) |
| H | Detector outlines reuse pooled canvas items; the camera list is built on a worker thread | No delete/recreate of outlines every frame; Refresh and backend changes no longer freeze the window |

### Notes

- **Database loading:** the Database tab shows "Loading …" until the catalogue is ready. Scans started before then run without the new database, as if it were not loaded yet.
- **Camera list:** the device box shows "Searching for cameras…" for a moment at startup. If Start is pressed before the list is ready, the status bar asks you to try again. If the camera driver refuses to be listed from the worker thread, the list is built on the window thread as in 0.8.3.
- **Existing scan logs:** records keep their `context.png` until a sharper image replaces it; it is then replaced by `context.jpg` and the record's `context` field is updated. **Export scan log CSV** follows that field.

## ICOCR 0.8.3.1 — selection rules prototype

Drop-in update for an existing ICOCR 0.8.3 folder (with or without the CUDA
cuDNN-search patch). Copy the files over the 0.8.3 folder and replace when asked.
No new dependencies, settings, data or database changes. Remove the files listed
below (or restore them from 0.8.3) to roll back.

### What changed

Only how the selected marking is chosen among text the OCR has already read.
Recognition, preprocessing, the database and matching are unchanged.

1. **Short block markings.** A 4-7 character code with one group of 2-3 letters
   and a 2-5 digit run (VP251, HC32, 2QP17, AHC08) can now be selected when it sits
   in a multi-line marking block (aligned neighbouring lines, as before) and reads
   at OCR score 0.95 or higher. One-letter codes (B663, P185, J803P) remain
   lot-shaped and are still not auto-selected.
2. **Strong markings first.** Unfamiliar text with two leading letters and a run
   of three or more digits (DA8950M, VP251, GAD311), or a 4-8 digit stem with a
   1-3 letter suffix (2903M, 9013M), outranks other unverified text. Previously
   only 6+ character syntax matches ("unknown" kind) had this priority.
3. **Lot/date-code penalty.** Unverified text with only single interleaved digits
   (A7LJG4) or a YYWW date prefix (2235D4, 1732A6; years 00-27) is ranked down by
   0.20 and never counts as a strong marking.
4. **Short codes below printed numbers.** New short block codes that are not
   strong are ranked 0.20 lower, so they do not displace a printed numeric
   identifier (73103) or a body/block number (2904, 3765).

Database-supported and part-syntax selections keep their existing priority.

### Known limits

Not addressed: conflicting spellings in one region (KQEXV9013D/KQEXV90131,
BTB06-600BW/BU, 6Y3360P/F) still abstain; one-letter codes (P185, C10T20F) and
4-digit numbers without body evidence (2531, 4468) are still not auto-selected;
character misreads (0S1307, 74HC1630) need the deferred database correction.
These rules were derived from a 74-image set and may need adjustment on new boards.

## ICOCR 0.8.3 — workshop documentation build

Extract into a new folder. Reuse the existing CPU environment or run `setup_windows.bat`, then `run_windows.bat run --device cpu`. Existing data remains in `%LOCALAPPDATA%\ICLens`. No new Python dependencies, database changes or ICBENCH patch are required. OCR recognition and matching code is unchanged from 0.8.2.9.

### Main window

Camera selection, Refresh, Start, Stop, Settings, Open image, Scan, Live recognition, Capture image and Logging remain accessible. The snapshot, recognized markings, session history and selected description remain in the side panel.

Database lookup, Saved matches, Datasheet and Save/Edit match buttons are removed. Existing saved-match data is retained. Unnecessary main-window hints are removed. CPU/OCR duration, camera resolution/FPS, and scan messages occupy separate fixed-width areas. Long messages clip inside their area instead of moving the other status indicators. The snapshot status also retains its fixed height.

### Settings

- Camera: DirectShow/MSMF, requested resolution/FPS and Request MJPG. Restart capture to apply camera changes.
- Recognition: chip detector and model, body crop, detector body source, fast scan, Original fallback, snapshot preprocessing, alignment correction and Show all recognized text.
- Database: load/reload and loaded-database status.
- Documentation: output locations, New IC, CSV export and save status.
- Tools: diagnostics and OCR runtime details.

Settings are retained on closing Settings or exiting the application. Logging starts off each session. Existing preprocessing policies and database selection retain their existing storage.

### Capture image

Saves the complete current input frame at its received resolution, before overlays, selection cropping, preprocessing or display resizing. Files are lossless PNGs named `IC_000001.png`, `IC_000002.png`, etc. Existing names are never overwritten, including after restart. A capture produces only the PNG: no metadata sidecar.

Destination: `%LOCALAPPDATA%\ICLens\captures`.

Works independently of Logging and duplicate suppression, including with an opened image. Every accepted click creates a separate image. Capture without an available frame reports that no image is available. The writer has a four-job limit; rejected requests and disk errors are reported, not silently counted as saved.

### Logging

Enable Logging before scanning. Applies to new manual scans and live OCR scans. Each encounter folder contains:

- `crop.png`: original selected scan region, without overlays or OCR preprocessing.
- `context.png`: the complete source frame corresponding to that scan region.
- `record.json`: observed markings (including fallback attempts), selected marking, resolved database part, timestamps, scan configuration and runtime information.

Destination: `%LOCALAPPDATA%\ICLens\scan_logs\<encounter>`.

Observed OCR strings remain separate from database identities. Empty/unidentified scans and OCR-error cases are saved too; error cases retain the error message. Repeated scans update one record and retain new distinct text. Repeated identical selection/configuration records are coalesced with a repeat counter. A sharper image can replace the existing pair; it does not add another pair. Sharpness is a heuristic measured at fixed thumbnail dimensions, not proof of legibility. Historical observations can therefore include text from an earlier image of the same encounter.

An encounter survives short visual disturbances. A sustained visual change (0.6 seconds), established tracking loss (1 second), a new region selection, stopping/opening a source, toggling Logging or New IC starts a new encounter. New IC is available in Settings → Documentation and through Ctrl+N. It also resets live retry suppression so the next scan can document the new encounter.

Two visually indistinguishable ICs cannot reliably be separated automatically. Use New IC for an indistinguishable replacement. Camera motion and lighting changes can split one physical IC into multiple encounters; this behavior needs workshop testing. Part number is never the deduplication key.

Logging captures the source frame belonging to the OCR request, not the later displayed frame. Disabling Logging prevents new logged requests; writes already submitted can finish. Frozen-image reprocessing does not create a new log record. Normal exit drains accepted background writes; scans cancelled during shutdown are not completed. A forced process termination can leave an incomplete encounter folder.

CSV export produces one row per completed encounter record, with observed markings, its latest selection/identity, and image paths. Export reflects records already committed when it is read; an active background update may appear in a later export.

### Workshop checks

1. Repeatedly scan a stationary chip with Logging enabled: one encounter folder and two PNGs should remain.
2. Move to another chip of the same type: verify separate records; use Ctrl+N for an indistinguishable replacement.
3. Scan an unreadable chip: verify its images and empty/unresolved record are saved.
4. Capture the full feed with overlays visible: the saved image must contain no overlays or crop and must match received resolution.
5. Restart and capture again: filenames must continue without overwriting earlier files.
6. Compare focus changes, brief occlusion, board motion and lighting changes for duplicate suppression.
7. Change settings, close/reopen Settings and restart the application; verify retained values. Restart capture after camera-format changes.
8. Verify FPS/resolution positions remain fixed during scanning and save notifications.

## ICOCR 0.8.2.9

Extract this archive into a new folder and run `run_windows.bat`. Existing settings and the external database remain in their existing locations. Point ICBENCH at this folder. No dependency or model-weight changes are required.

### Snapshot fallback

Select Snapshot preprocessing → fallback → snapshot. The new default sequence is Local contrast, Original, Illumination. Existing saved policies are preserved; Gamma and Invert remain selectable. Standard remains the default pipeline. Live scanning retains its existing preprocessing policy.

Fallback now compares eligible selections across attempts even when the database has no matching record. Empty or weaker initial results no longer automatically defeat later unmatched readings. An unmatched challenger must score at least 0.90 to replace an incumbent or an abstention. Ranking uses exact database evidence, other trusted database evidence, bounded part syntax, family hints, contextual/numeric evidence, then other eligible markings. Within the same tier, a later attempt needs an OCR score improvement greater than 0.05 to replace the incumbent. This is a conservative heuristic, not a calibrated probability.

Fallback stops on a conflict-consistent database-supported selection, or a bounded part-syntax marking with score at least 0.96. Other eligible unmatched readings may still win after the sequence finishes. An early stop is not proof that a reading or identity is correct. Attempts do not add votes or increase confidence. Each attempt retains its raw readings and full selection decision in diagnostics; the final display and transcription come from one selected attempt.

Diagnostics distinguish identity resolved, marking selected with identity unresolved, selection unresolved, and no text recognized. They record stop reasons and why each attempt replaced or retained the incumbent. Fast crop mode continues to reuse detections and skips retries when no crops were detected.

### Corrections

A one-character change inside a suffix that is then removed cannot justify a corrected base match. For example, `74HC1630` no longer changes 0 to O merely to match the base `74HC163`.

0/D is now a bounded database suggestion. Automatic use requires a unique full database record, recognized part syntax, and OCR score at least 0.95. Corrections retain the observed OCR text. Existing pairs retain their 0.90 minimum. Unique correction eligibility considers both the database identity and the corrected spelling. Corrections inside a known base can still retain an unchanged printed suffix.

DS plus four digits and M29W plus three digits have bounded syntax hints. These hints do not establish identity. The supplied low-score `0S1307` and `M29WB00FB` examples are not promoted automatically; truncated `MCS6F` is not completed from a database guess. A database containing only a base cannot verify an unread suffix.

Alias fields, alternate-marking data, CUDA repairs and OCR model changes are deferred. Annotation labels have not been changed.

### ICBENCH

Install ICBENCH 0.5.1 to include all attempts in raw-recall diagnostics and view concise per-attempt reasons. Final recognition, primary selection and identity scoring remain separate. Use the complete dataset, the same frozen database, fast/full mode, CPU environment and capture disabled for timing comparisons.

## ICOCR 0.8.2.8 — selectable snapshot preprocessing

Extract into a new folder. Use the existing CPU environment through ICOCR_PYTHON, or run setup_windows.bat to create a local CPU environment. To force CPU with the application launcher:

```bat
run_windows.bat run --device cpu
```

Set ICBENCH's ICOCR folder to this release before preprocessing experiments. This update adds no dependencies and retains the 0.8.2.7 character-correction and fixed snapshot-status layout changes. Existing data in %LOCALAPPDATA%\ICLens is retained.

### Controls

Snapshot preprocessing opens an editor with:

- standard: existing adaptive pipeline, unchanged default.
- single: one explicit preset, with no automatic treatment retry.
- fallback: ordered comma-separated preset names, maximum five independent attempts.
- stage snapshot: process the original selection before detection.
- stage crop: detect on original pixels, then process extracted text crops before recognition.
- gamma and background sigma parameters.
- Load ICBENCH policy: accepts an exported policy or generated benchmark run config JSON.

Use exact preset names: Local contrast, Original, Illumination, Gamma, Invert. The shared API also retains Lighting correction, Sharpen and Threshold. Illumination is background division only; Lighting correction also applies local contrast. Gamma below 1 brightens.

Applied settings are stored in %LOCALAPPDATA%\ICLens\preprocessing.json. They apply only to frozen snapshots; live recognition retains its existing policy. Changing the configuration invalidates an in-flight selection. The queued snapshot captures its own configuration, and cancellation is checked between inference operations.

The snapshot thumbnail previews the first preset for snapshot-stage processing. For crop-stage policies it shows original pixels; actual crop processing can be inspected in ICBENCH. The OCR diagnostics window records configuration, selected preset, each attempt and timings.

### Fallback semantics

Each attempt starts from the original snapshot or original detected text crop. Attempts do not combine into extra confidence votes. Stop at the first accepted result: a selected, non-provisional, conflict-consistent database match when a catalogue is loaded; otherwise a selected marking with OCR score >= 0.90. These scores are not calibrated probabilities. A confidently wrong accepted match can stop retries.

If no attempt is accepted, retain the first attempt's output. Fast crop-stage fallback detects only at 0/90 degrees once per snapshot and reuses the resulting crops. Full mode supports crop transforms but repeats detection. If fast crop detection finds no text, crop retries are skipped. Snapshot-stage presets each rerun detection.

Retries run in the existing background worker, with at most five preset attempts. A single native inference cannot be interrupted mid-call. Optional auto-body cropping can still perform its existing full-selection recovery, which may execute another bounded policy on that separate crop. ICBENCH does not apply auto-body cropping; disable it in ICOCR or benchmark equivalent saved crops when comparing results.

Explicit preprocessing experiments surface inference/provider errors; they do not silently rerun a failed experiment on a different device. Standard mode retains its existing CPU fallback behaviour. The CUDA configuration issue is not addressed.

No fallback order is promoted as a production default. Standard remains selected until the user changes it. Validate full-dataset regressions in ICBENCH before choosing a policy.

## ICOCR 0.8.2.7

### Character corrections

One-character alternatives are checked against the loaded database using these
symmetric confusion pairs: 0/O, 1/I, 1/L, 5/S, 8/B, 2/Z, 6/G, 1/T and I/T.
T substitutions receive a lower heuristic cost in the bounded 74/54-series
HC/AHC/AC technology field. Costs are ranking heuristics, not learned probabilities.

Examples: 74HC1273D or 74HCI273D can resolve to 74HCT273D when that entry exists.
A known 74HCT273 base can also resolve the reading without asserting its package.
ULN2O03 can resolve to ULN2003; LM35BN can resolve to LM358N.

Automatic correction requires one unique database identity, a recognised part
pattern, at least six characters and OCR score >= 0.90. That score is an OCR
engine score, not a calibrated probability. Existing exclusion, orientation and
conflicting-identity checks remain active. Literal trusted matches take priority.
Multiple valid identities remain suggestions even if one has a lower cost.
Shorter readings can receive suggestions; numeric-only readings are excluded.
There are no insertions, deletions or multi-character repairs.

Raw OCR text is preserved in results and diagnostics. The overlay and result list
label corrected identities explicitly. Selecting a corrected result searches its
resolved database part number. Diagnostics report the changed character and cost.
The benchmark selected_marking remains the raw reading; resolved_partnumber
contains the database identity. This does not artificially improve raw OCR scores.

Correction uses bounded dictionary lookups, without another model call or a full
catalogue scan. Existing line rereads, tracking and recovery remain in place.
Database absence is not proof that a part does not exist: these remain labelled
corrections to inspect against the image, rather than confirmed physical identity.

### Snapshot status layout

The snapshot status has a reserved 48-pixel container. The longer
"full selection — Body touches selection edge" message can wrap without moving
the controls below it.

## ICOCR 0.8.2.6

### Performance changes

1. Optical-flow/appearance processing for overlays runs in a dedicated worker.
   Tk submits the newest frame and draws already published coordinates. A single
   consecutive-frame transform advances text and body geometry; a short transform
   history handles newly arriving tracking results without repeating image work.
   Direct source-frame checks reanchor geometry every eight processed frames.
2. Geometry and transforms publish atomically. The UI can continue showing the
   previous valid projection when a newer tracking result arrives, avoiding a
   new source/old transform mismatch. Video always uses the newest camera frame.
   Publications may lag the camera; those older than 180 ms are hidden.
3. A latest-frame mailbox replaces pending work rather than building a queue.
   Epoch reset discards old results. Shutdown joins the worker outside Tk.
4. Live OCR completes its initial orientation search, retaining existing confident
   early exit. Optional retry/deskew passes are bounded by an 800 ms elapsed-time
   budget checked between model calls. This is a soft extra-work budget, not a
   maximum scan duration. Individual inference cannot be interrupted.
5. Subsequent unresolved live attempts alternate Local contrast and Original as
   their initial treatment when Targeted Original is enabled. Slow machines still
   get Original-image attempts even when the previous scan spent its retry budget.
   Frozen scans retain the preceding orientation/treatment policy.
6. Requests invalidated by user actions or a lost live snapshot acquisition stop
   between model calls. Cancellation does not disable Live or trigger CPU fallback.
7. Diagnostics add rolling median/p95 (up to 240 samples) for UI, worker, rendering
   and recognition timings. Fast mode reports separate text detection/recognition
   totals. Counters include full_scan_requests, recovery_count and cancelled_scans;
   live_budget_limited records skipped optional work.

### Sticky lock recovery

The state sequence is tracking -> reacquiring -> tracking or fresh acquisition.
On tracking failure the previous reading, database result and vote are retained
for up to 750 ms. A recent marking template is searched inside the selected ROI,
without OCR. Matching requires correlation >= 0.90, a gap >= 0.08 over a competing
location and confirmation on two newly processed frames. Repeated submissions
of the same frame sequence cannot confirm recovery.

Successful reacquisition restores tracking and preserves the reading vote.
Full OCR remains blocked during recovery. Failure/expiry clears the retained
vote and returns to the existing stable-scene acquisition policy. Changing ROI,
source dimensions or epoch cancels recovery. No positional label is held blindly
while location is unknown; the status says Reacquiring IC.

Recovery searches translation at the current scale. Large rotation/zoom, blur,
low texture and occlusion can still require fresh OCR. Duplicate appearance
peaks are rejected, but a visually indistinguishable replacement cannot be
excluded from images alone. Appearance recovery is not new identity evidence.
The thresholds need validation on the actual microscope feed.

## ICOCR 0.8.2.5-p1 — moving overlays

### Cause and fix

0.8.2.5 tested whether each worker's source frame was stationary relative to
the current camera frame. Normal movement failed that check, hiding both OCR
and body outlines until the next worker update, then hiding them again.

The patch projects delayed geometry onto the current frame using sparse
optical flow and a robust translation/rotation/scale fit on images capped at
320 pixels on the longest side. Text, associated body polygons and detector
polygons use the same projection method. Detector hit-testing uses the moved
bounds. Source results remain unchanged; projected coordinates never feed back
into recognition, tracking or the body inference cache.

Frame-pair transforms are cached within each rendered frame. Video continues
to use the newest camera frame. The stationary inference cache remains strict.
The display allows up to 500 ms for text geometry and 750 ms for body geometry,
subject to motion verification, so normal worker latency does not trigger the
old 250/300 ms cutoffs. Exact source-frame geometry remains valid for a still.

Forward/backward flow agreement, feature inliers, bounded motion and warped
image residual checks reject unreliable projections. Occlusion, large movement,
insufficient texture, scene replacement and result expiry can still hide an
outline. The patch does not blindly hold an old identity over a new chip.

Diagnostics expose overlay_motion_ms, the latest uncached projection time.
The routine runs in the display path and adds CPU work during movement.

## ICOCR 0.8.2.5

This release addresses preview framerate with body detection enabled and avoids
redundant body inference. OCR selection logic, model weights, dependency versions
and the 0.8.2.4 evidence fixes are unchanged.

### Changes

- Preview always renders the newest available camera frame. Previously,
  alignment mode substituted the detector's source frame, tying visible video
  updates to detector throughput. Recent tracking results could also substitute
  an older frame. Both substitutions are removed.
- Body and text outlines can reuse recent coordinates after a cheap motion
  check. Changed views hide delayed outlines instead of freezing video. Body
  overlays expire after 300 ms without a worker update; text after 250 ms.
  Exact source-frame results remain usable for a static image.
- Overlay and body-crop requests share a serialized inference cache. Stable
  views reuse results for up to 750 ms after inference completes. Shape,
  preprocessing, or motion changes require fresh inference. Each detector model
  owns its cache. References stay anchored to inferred pixels, avoiding drift
  through a chain of successive cache hits. Cached geometry is copied on return.
- Background body detection pauses while OCR is busy and drops pending frames.
  In-flight inference can finish; it cannot be interrupted. When resumed, the
  existing latest-frame mailbox processes the newest submission. No faster
  inference cadence is imposed during motion.
- Queued OCR requests from an invalidated scene finish as cancelled without
  running inference, while still clearing the busy state. A full scan mailbox
  cannot block the UI.
- The UI's nominal 33 ms tick budget includes processing time instead of adding
  an unconditional 33 ms after processing. This is a target, not a guaranteed FPS.
- Diagnostics add preview_fps, ui_tick_ms, motion_gate_ms, body_cache_hit and
  body_cache_age_ms. detector_ms measures the latest worker operation, including
  a cache lookup when body_cache_hit is 1. Existing OCR and rendering timings remain.

The motion gate is a conservative low-resolution heuristic, not optical flow or
a proof of identical geometry. Noise can cause extra refreshes; very small motion
can pass the gate. Short expiry and anchored references bound reuse. Live checks
are still needed with the actual microscope, lighting and camera resolution.
Existing tracked-line OCR and orientation hints are retained; this release does
not redesign text detection or change recognition thresholds.

### Live comparison

Run 0.8.2.4 and 0.8.2.5 with the same device, resolution, exposure, database and
camera position. Allow model warm-up. For each release compare:

1. Preview with body overlay off, then on with alignment corrections on.
2. Live OCR with Body from chip detector enabled; hold one known chip still.
3. Move or rotate the board, then hold still on a different chip. Video should
   keep advancing; delayed outlines should hide, then recover. Recognition must
   update to the new chip rather than retaining the previous identity.
4. Compare preview_fps, rendering_ms, ui_tick_ms, detector_ms/cache hit and OCR
   total_ms. Record both stationary and moving views. Diagnostics values are
   snapshots, not whole-session averages; preview_fps counts rendered updates,
   not frames delivered by the capture driver.

The main acceptance criterion is smooth preview with detection enabled while
maintaining the correct part selection observed in 0.8.2.4.

## ICOCR 0.8.2.4

This release repairs selection and evidence retention using the existing OCR
models, detector and database matching rules. No model weights or dependency
versions change.

### Changes

1. Full mode no longer discards the initial, uncorrected OCR observations when
   deskew adds more passes. Both sets retain their original-image coordinates.
2. Candidate pooling retains every observation's geometry and provenance.
   Nearby marking evidence can survive a later high-score box whose reading
   direction differs. New captures require supporting lines from the same pass.
3. A clearly weaker opposite-direction reading can no longer automatically
   veto a strong candidate with bounded part-number syntax. The winner needs
   at least 0.95 confidence, the challenger below 0.85, and a gap of at least
   0.15. These are conservative heuristics, not calibrated probabilities.
   Comparable readings, same-direction conflicts, purely numeric strings and
   broad family prefixes retain the conservative conflict behaviour.
4. An eligible prior selection survives a near-equal, same-tier replacement
   after deskew or retry. A newly credible conflict still blocks selection;
   stronger identity/syntax evidence can replace it. This is not unconditional
   first-result locking.
5. Mixed device-like marks retain aligned-block support across observations.
   Short alphabetic marks require number-bearing lines on both sides, reducing
   confusion with a logo above a code stack. Four-digit block geometry retains
   conservative spacing/size gates. Country text and PCB references stay excluded.
6. Diagnostics expose observation_evidence, pass_id, crop_id, detection_turn,
   deskew_degrees, conflict_evidence, dismissed_conflicts and incumbent_retained.
   Rotations and treatments from one image are not reported as independent frames.

### Tests and limits

- Actual CPU inference: synthetic LM358 at 0 and 20 degrees selected correctly
  in both fast and full mode. The diagonal full scan retained its initial
  observations and completed eight passes. This is a smoke test, not an IC
  accuracy benchmark.
- Windows GUI/camera and CUDA were not run here. No end-to-end latency
  improvement or full-dataset release score is claimed.
- The benchmark database and current photographs were not included in the run
  archives. Identity accuracy remains unscored and ground-truth annotations
  were not changed without image review.

Replay command (strict by default):

Use --skip-incomplete only to produce a partial report: cases needing uncaptured
database replies are explicitly unavailable and excluded from paired scoring.

## ICOCR 0.8.2.3 — focused selection fixes

### Changes

- Country/origin words are retained in raw OCR and diagnostics but excluded
  before automatic candidate database lookup and primary selection. Exact words:
  JAPAN, MALAYSIA, MEXICO, CHINA, TAIWAN, KOREA, THAILAND, PHILIPPINES,
  SINGAPORE, INDONESIA, USA, GERMANY. Exact MADE IN, ASSEMBLED IN, PRODUCT OF
  phrases and their country combinations are handled. Mixed lines retain other
  tokens. No fuzzy/substring blacklist or short manufacturer-code blacklist.
- BCP followed by two/three digits and bounded suffix syntax is a part-format
  hint, not proof of identity. It can compete with unrelated broad family hints.
- Bare W + digits + zero/two trailing letters remains selectable, but its broad
  family hint no longer outranks a supported block marking. Trusted database
  matches retain priority. No date-code string is hardcoded from the benchmark.
- Observed printed lines, selected normalized marking, and resolved database
  part number are exposed separately. Candidate details show observed text.
  Wrapped ADM34 + 83ARZ still selects ADM3483ARZ; its database identity can be
  ADM3483. The join is supported by two actual printed lines, not guessed text.
- Duplicate raw output is merged only for identical overlapping text in the
  same reading direction/treatment. Identical text at separate positions stays.
  All individual readings remain in raw_observations. Geometry is now attached
  to fast/full OCR raw readings. Existing ICBENCH 0.4.0 consumes the cleaned raw
  view without an adapter replacement.

### Install and benchmark

Extract ICOCR_0_8_2_3 into a separate folder. Reuse the already working Python
GPU environment using ICOCR_PYTHON as documented in README.md, or run the usual
setup. No dependency/runtime/CUDA installation changes are made in this release.
Existing user settings and the external database remain in their usual locations.

Point ICBENCH's ICOCR root at the new folder and retain the same images, database,
annotations and fast-mode settings for the comparison. The next full run is
required to measure end-to-end accuracy, duplicate-line output and latency.

The existing exact-primary scorer still treats a valid multi-line ADM3483ARZ
join as different from an ADM34-only primary annotation; this release does not
alter annotations or hide that distinction. Populated identity labels must have
identity_status=verified before ICBENCH scores them.

## ICOCR 0.8.2.2 — detector integration and Original fallback experiment

### Detector changes

The supplied ic_body_obb.onnx and JSON are bundled unchanged. The SHA-256 matches
the JSON, the ONNX graph validates, and CPU inference returns finite output with
shape 1 x 6 x 8400. The model was not retrained.

Two integration changes are controlled by **Detector alignment corrections**
(default on):

- Resize detector inputs with linear interpolation, matching Ultralytics 8.3.200
  LetterBox. The preceding build used area interpolation when shrinking images.
- Pair the detector polygon with its actual source frame. Previously polygons
  up to 15 frames old could be drawn over the current camera frame or a separate
  OCR tracking frame. When displaying a tracked OCR result from another frame,
  the incompatible detector overlay is hidden. Without a tracked result, the
  detector view uses the detector source frame while recent enough (at most 15
  frame IDs behind and 0.5 seconds since completion). Stationary loaded images
  keep their overlay. Detector view refresh therefore follows detector cadence.

Turning this switch off restores the preceding resize and overlay behaviour.
Frame-pairing changes affect display; detector-to-OCR body crops continue to
require detections from the exact requested frame and model. Cached detections
must now also match the preprocessing mode. Changing modes invalidates pending
worker results. Separate inference calls do not mutate shared detector settings.

No arbitrary angle offset, width/height swap or square-angle snapping was added.
The corner conversion matches the numpy branch of Ultralytics 8.3.200 exactly
for all 8400 raw candidates from a synthetic-image ONNX run. Independent tests
compare decoded squares and rectangles against OpenCV rotated rectangles over
multiple angles, aspect ratios and padded input shapes.

**The reported static square-package misalignment is not confirmed fixed.**
There is no failing source photograph or matching native prediction in the
provided files. Matching the preprocessing removes a known difference; it is
not evidence that this difference caused that specific failure.

### Targeted Original fallback

**Targeted Original fallback** defaults on and is independent of detector
alignment corrections. It replaces the existing retry treatment for these cases:

- No automatically selected marking.
- A high-confidence family/unknown identifier still has an unresolved spelling
  conflict, even if another line was selected.

Original scans both detection axes in fast mode (0/90 degrees, each detected
line recognised both ways), or all four rotations in full mode. It does not
stop early during this retry. It merges observations using the existing text-
region overlap rules, then reruns selection. Conflicting spellings are retained;
repetition alone does not establish which spelling is correct.

Strong successful scans without a relevant conflict do not take this fallback.
Weak selected results retain the previous one-orientation retry. Turning the
switch off restores the 0.8.2.1 retry policy; it does not disable all retries.

Diagnostics expose targeted_original, retry_reason and retry_detection_passes.
retry_calls counts retry treatments, not detector or recogniser invocations.
This is one retry treatment per OCR read. Existing failed-body recovery can
perform another full-selection OCR read, so total work may exceed two passes.
Original refers to image treatment: body masking, resizing and line extraction
still apply. A confidently wrong selected marking can bypass this fallback.

### Controlled comparison

Run the same dataset/database/settings with both switches off, alignment only,
fallback only, and both on. Record correct/wrong/empty outcomes, retry frequency
and total latency. Detector changes require detector-body cropping to affect
OCR results; overlay-only mode affects display. Geometric auto-body cropping is
unchanged. Benchmark raw Original separately as before.

For non-GUI integrations constructing the OCR/detector classes, environment
variables set defaults before launch:

```bat
set ICOCR_TARGETED_ORIGINAL=0
set ICOCR_DETECTOR_ALIGNMENT=0
```

Use 1 to enable each. The GUI switches override these defaults for that session.
No changes to the external ICBENCH application were made; ensure it imports this
build and does not override the selected settings.

### Frozen-frame diagnostic

With the ICOCR Python environment active:

This saves legacy/aligned model inputs, source-image overlays, input-space
polygon overlays, raw ONNX output arrays and a JSON report. The numbered corner
positions help distinguish rotation from display placement. It runs on CPU and
does not involve the GUI, camera or tracker.

Optional native comparison requires a separate environment with Ultralytics
8.3.200 and this project's dependencies:

Without --native-model, native inference uses the same ONNX. With matching .pt
weights it also exposes export differences. Comparison uses fixed 640x640,
rect=False. Native default auto-rect settings may otherwise yield different
input shapes. Native probabilistic OBB NMS and ICOCR polygon-IoU NMS can retain
different candidates; different counts do not alone prove bad angle decoding.
Ultralytics is not added to application dependencies.

## ICOCR 0.8.2.1

This release changes selection of recognised markings. It does not replace the
OCR model or train on the supplied images.

### Changes

- Admit high-confidence unfamiliar mixed markings when nearby parallel text
  supplies block evidence. Numeric stems with letter suffixes and longer
  letter-led mixed identifiers can qualify. Short alphabetic markings require
  two distinct nearby number-bearing lines and higher recognition confidence.
- Derive block alignment from physical text-box geometry. OCR rotation labels
  alone do not determine whether lines belong together. Overlapping alternative
  readings and PCB reference designators cannot supply this support.
- Prefer established families and existing unknown identifiers over newly
  admitted contextual markings. A small ranking preference helps longer
  letter-led mixed markings compete with numeric-led lot codes.
- Withhold an unmatched numeric fallback while a high-confidence family or
  unknown identifier has unresolved spelling conflicts. Preserve trusted
  catalogue selections and existing identity-consistency checks.
- Expose contextual eligibility and numeric-withholding reasons in diagnostics.
- Add a reusable saved-observation replay tool and its 39-case evidence report.

This is evidence of a printed marking, not proof of component identity. Isolated
four-digit codes still need the existing body/numeric-block evidence; 2531 is
not globally whitelisted. Manufacturer prefixes and catalogue suggestions are
not converted into confirmed identities.

### Saved-observation replay

| Selection outcome | 0.8.2 | 0.8.2.1 |
| --- | ---: | ---: |
| Correct | 23 | 26 |
| Wrong | 10 | 8 |
| No selection | 6 | 5 |

Recovered 9013M, LHNK and D83A04EF. The conflicting KQEXV9013D/KQEXV90131 case
now stays unresolved instead of selecting 16127378. All previously correct
selections remain correct. No missing catalogue replies were needed.

These figures reuse recorded OCR candidates and catalogue responses. They are
not a fresh OCR run, a latency measurement or an independent accuracy estimate:
these same cases informed rule development. Live retry behaviour may also
change when selection changes. Run a fresh ICBENCH comparison on the same images
and an untouched dataset to measure the complete application.

The unchanged ADM34 labels remain as supplied; possible label problems were not
used to adjust the score. Missing OCR readings cannot be recovered by these
selection rules alone.

## ICOCR 0.8.2

This release changes selection around the existing OCR pipeline. It does not
replace the recogniser or detector, add preprocessing treatments, infer missing characters,
or treat a family prefix as a database identity.

### Behaviour

- Trusted exact/base database evidence retains priority.
- Eligible bounded part-number patterns rank ahead of unstructured mixed codes
  and numeric-only markings. Existing broader family hints are the next tier.
  OCR score and treatment support break ties within a tier.
- Added specific syntax support for BTS/BTT/BTF, SP interface numbers, LA,
  LM, selected 74/54 logic, ULN/ULQ arrays and serial EEPROM families.
- A complete line such as `BTS 740 S2` becomes the candidate `BTS740S2` while
  preserving the original line and its box. Only whitelisted whitespace
  boundaries are joined. Logos, separate boxes, trailing numeric date codes
  and arbitrary neighbouring tokens are not concatenated.
- A lower-scored reading direction can remain selectable without a database
  match when it has a bounded part pattern, score at least 0.85, no character
  conflicts, and an overlapping opposite-direction winner with no recognised
  family/database evidence and a score advantage no larger than 0.12.
  These are initial heuristic limits, not calibrated probabilities. Two
  plausible part readings are not resolved by this rule.
- An unstructured mixed code no longer causes an immediate no-database live
  early exit before remaining orientations are checked. Numeric-only fallback
  behaviour is retained.
- Diagnostics now distinguish selected, lower priority and rejected candidates,
  showing selection tier, score, support, rank and whitespace-joined source text.

The existing confidence floors, short-resistor/reference exclusions, character
conflict checks and database identity restrictions remain in place. Unknown and
numeric fallback markings remain available. This is an initial ruleset, not an
exhaustive IC naming catalogue.

### Use and benchmark

Extract the release into a new folder and use `run_windows.bat`. The existing
SQLite catalogue and runtime data need no migration. Reuse an existing Python
environment via `ICOCR_PYTHON` as described in README.md.

Run the same 39-image ICBENCH dataset after configuring its ICOCR source to this
release, if that build supports an external source directory. An ICBENCH build
with a bundled copy of ICOCR must update that copy first; simply extracting this
archive does not update ICBENCH. No ICBENCH adapter was changed in this release.

Inspect selection diagnostics for failures. Measure correct primary selections,
wrong selections and no-selections separately. Retain a separate untouched test
set to detect overfitting to the examples that motivated these rules.

## ICOCR 0.8.1 — database priority

Generic substring matches remain visible as suggestions but no longer create an automatic database identity, gain a database ranking boost, hide an unmatched marking, or confirm a tracked identity. This applies consistently to the candidate list, overlay, retry policy and session-history upgrades.

Exact matches keep priority. A printed base followed by 1–3 suffix letters can resolve the literal base already present in the catalogue; it does not invent a complete SKU. Multiple possible suffix variants remain suggestions. Clear part-like printed prefixes of such variants can keep acquisition pending rather than locking onto another line, but do not resolve identity. Existing pending exact/base evidence still supports retrying a plausible part instead of selecting a lot code.

The database itself is unchanged. No model weights, thresholds for package detection, or general marking-format rules were changed.

## ICOCR 0.8.0 — project cleanup

Based on 0.7.9.2. No detector weights or OCR thresholds changed.

- Replaced 12 batch scripts with `setup_windows.bat [cpu|cuda]` and one
  `run_windows.bat` command entry point. Removed hard-coded old-version paths.
- Added `manage.py` dispatch for run, tests, evaluation, detector validation,
  replay, strict GPU check and CPU/GPU benchmark.
- Fixed GPU diagnostic/benchmark project paths and shared user-data paths.
- Fixed detector validation to default to the bundled OBB model.
- Kept one dependency manifest; CUDA setup replaces RapidOCR's transitive CPU
  runtime after dependency installation so only the selected backend remains.
- Removed unused legacy scene-signature helpers and write-only controller fields.
- Removed the unused two-scan overlay-confirmation implementation. The scene
  guard now owns only stability detection; ReadingVote continues to own live
  text agreement. Two tests specific to the retired implementation were removed;
  movement, drift, controller and current voting coverage remains.
- Reused the shared OCR token parser in the full-scan branches.
- Made numeric-family lookup a normal Catalog method instead of a monkey patch.
- Updated model integration metadata and removed the training-machine path.
- Corrected the detector smoke-test gate to test the bundled OBB model rather
  than skip because the obsolete upright model is absent.

## ICOCR 0.7.7.2 — status, persistence and evaluation

- Display capture errors and scan status in the video area and bottom status bar; expose processor and GPU-fallback reasons after scanning.
- Log and search a rapid double-click once.
- Move click logs and new snapshots to `%LOCALAPPDATA%\ICLens`, outside release folders. Merge older click logs from the current and sibling ICOCR folders once, preserving original files. Older snapshot directories are not moved.
- Add Open data folder.
- Add an image evaluation tool covering correct/suffix/wrong/empty selections, negative-image false positives, raw/list visibility, latency and OCR call count. Include CPU/no-database full-selection and body-crop baselines.
- Recognition, matching, body cropping and tracking are unchanged from 0.7.7.1. The 17-image development set is too small to establish general accuracy.

## ICOCR 0.7.7.1 — experimental automatic body cropping

- Locate approximately rectangular central bodies using edges, grayscale/colour segmentation, boundary contrast and shape. Detection runs per scan on a thumbnail capped at 640 pixels; OCR retains source resolution.
- Neutralise pixels outside the body and require text-box overlap of at least 80%. Map body outlines and OCR geometry back into tracking; show cyan body outlines and diagnostic rejection reasons.
- Reduce the minimum contour area from 7.5% to 2% after two supplied failures with bodies occupying approximately 5% of the selection. Add colour/Lab support and consolidate duplicate proposals more tolerantly.
- Fall back to the original selection when a body is clipped, indistinct or ambiguous. A detected body with no readable marking does not automatically retry the full selection.
- This is experimental geometric filtering; rectangular passives can qualify. No general accuracy gain or package identification is established.

## ICOCR 0.7.6.1 — ambiguous descriptions

- Display one representative database description followed by `*` when variants or descriptions differ, preserving alternatives in details.
- Choose by exact match, closest name length, longer name on a tie, then alphabetical part name/description. Conflicting descriptions for exact matches use amber overlays.
- Permit same-region suffix-conflict resolution only when observed variants resolve to the same set of database parts.
- Retain the indexed matching, asynchronous tracking, bounded retries, rendering reuse and shutdown improvements from 0.7.6.

## ICOCR 0.7.6 — indexed matching and asynchronous tracking

- Build a startup index of legal prefix/suffix removals, bounded to three characters per side. Keep exact matches first and use a bounded LRU cache instead of rescanning all database names on misses.
- Reuse the previous successful OCR orientation; examine only remaining rotations on recovery. Keep deskew and one bounded preprocessing retry.
- Group readings by physical text position. Separate rows do not automatically conflict; identical text at separate positions retains separate boxes. Rotations do not count as independent evidence.
- Resolve same-region suffix conflicts only when all readings identify the same single database part. Pending plausible database evidence blocks lot-code locking.
- Publish one structured result for list, history and overlay, including rejection reasons.
- Move optical flow, snapshot mapping and label initialisation to a latest-frame tracking worker with generation/request/frame IDs and stale-label rejection.
- Limit unresolved/provisional acquisitions to three extra scans at approximately 0.5, 1 and 2 seconds. Scene/ROI/database/source changes and explicit Scan reset the acquisition budget; database matches stop retries.
- Reuse canvas/overlay objects and unchanged frames; process snapshot previews at preview size.
- Add per-stage diagnostics. Drain OCR before closing snapshot saving and wait without blocking Tk.

## ICOCR 0.7.5.5 — wrapped markings and matching hotfix

- Join adjacent aligned lines such as `ADM34` + `83ARZ` when geometry, spelling and an exact/unique base database match support the join. Preserve original readings and add no OCR passes; confident exact joins can use early exit.
- Permit suffix conflicts to resolve a base part when every observed spelling resolves to the same single database part; retain raw conflicts.
- Prevent unresolved plausible database evidence from locking onto a lot/date code. Prioritise its orientation for the bounded retry and preserve it through generic filtering.

## ICOCR 0.7.5.4 — optional snapshot saving

- Add a Save snapshots checkbox, unchecked on launch and not persisted.
- Save only new scans with detected text; already running scans may finish saving after the checkbox changes. Preserve existing images.
- Leave recognition, previews, tracking and overlays unchanged.

## ICOCR 0.7.5.3 — live scan scheduling

- Reduce stability wait from 200 to 60 ms and post-result pause from 100 to 30 ms, excluding camera/UI scheduling.
- Stop live rotation search on a non-conflicting exact database match at score >= 0.90, or a valid unmatched marking at >= 0.95 when no database is loaded. Unknown/date codes and partial matches cannot stop early with a loaded database.
- Load models in the background; cache partial lookups and invalidate the cache on reload.
- Retain manual full-orientation scans, source-resolution snapshots and bounded weak-read retries.

## ICOCR 0.7.5.2 — numeric markings and selective retries

- Admit 5–12-digit numeric markings at OCR score >= 0.92 as unidentified markings; they may be lot/date codes. Numeric lookup requires an exact database entry.
- Continue excluding 1–4-digit numeric markings and PCB references from automatic overlays while retaining them for inspection.
- Retain unfamiliar mixed letter/number markings without database matches.
- Give weak/empty/conflicting results at most one extra OCR call at one selected orientation: Original for plausible text, otherwise Lighting correction. Merge evidence while preserving conflicting spellings.
- Strong results avoid treatment retries. No dependencies were added; real accuracy and GPU-speed gains were unmeasured.

## ICOCR 0.7.5.1 — snapshot archive

- Archive source-resolution, unprocessed lossless PNG crops after nonempty OCR, including rejected/unmatched text. Use unique date/time/sequence/mode/ID filenames in the historical installation-local `snapshots/` directory.
- Exclude blank/error scans, frozen-image rereads and continuous video frames. Do not encode OCR guesses into filenames.
- Write in the background, report saved counts/errors and drain accepted saves on normal exit. Clearing history does not delete archived images.

## IC Lens history (before ICOCR)

### Earlier tracking and session-history baseline — exact introduction versions unspecified

- Lock from one clear frozen snapshot; map the result to the current target, follow with optical flow and pause OCR while tracking. Preserve sidebar recognition if location is lost; clear positional labels when their location cannot be established.
- Track across the visible frame beyond the acquisition region. Retain the old label while acquiring a new target; track one label at a time.
- Cache orientation hints and restart acquisition after target loss or explicit state changes.
- Maintain an in-memory, first-seen session history with one row per marking and stronger database-description upgrades. Allow independent history browsing, web searches and clearing.
- Exclude short numeric resistor-like codes and PCB reference designators from automatic recognition; expose them in raw/show-all views. Historical exact/partial/unmatched overlay priorities were superseded by later releases.
- Source reports a 58-test 0.7.4 baseline and five passing snapshot/acquisition integration tests. Synthetic tracking measured about 4.7 ms median / 5.7 ms worst; historical 0.7.0 OCR examples measured 0.98 s full-orientation and 0.25 s cached-orientation. These exclude capture/display and are not Windows/GPU guarantees.

### IC Lens 0.5.4 — two-column click CSV

Clicks append to marking_clicks.csv beside app.py.
Only two columns: marking,in_database
Database status: yes or no; unknown if no database is loaded.
Open click log folder now opens the app folder.
Existing CSV rows are preserved. The older detailed log is no longer written;
it remains in %LOCALAPPDATA%\ICLens\marking_clicks.jsonl and is not migrated.

Python compilation and two-column CSV append checks passed.
Windows GUI has not been run here.

### IC Lens 0.5.3 — recognised-marking click history

Every valid mouse click on a recognised-marking row appends a record to:
%LOCALAPPDATA%\ICLens\marking_clicks.jsonl

Use Open click log folder to find it. The file is UTF-8 JSON Lines: one JSON
record per click. It persists across restarts and application updates. Records
include local timestamp with UTC offset, unique event ID, marking, original OCR
token, score/status, function, family hint, matched database evidence, database
path, snapshot time label and web search URL. No snapshot image is stored.

The second click of a rapid double click is logged too, with its repeated search
marked suppressed. One browser search is requested. Repeated clicks later create
new records and searches. Clicking empty space or programmatic result updates
does not log an event. Keyboard selection alone does not constitute a click.

search_requested records the intended browser action; it is not proof that the
browser loaded the page. The log is written before requesting the search. Write
failures display an error; searching remains available even if logging fails.
The log grows without automatic deletion. It contains search history and local
paths, so share it only when intended. Database evidence is captured at click time.

### IC Lens 0.5.2 — component functions

Matched markings now show the recorded function directly in the results list.
Use the horizontal scrollbar for long descriptions. Clicking a row still opens
its web search, and also shows the function in the detail panel and overlay.
Database details shows component-level and source-entry functions separately,
with the existing manufacturer, package/interface and source references.

If matching records contain different nonempty descriptions, the list says
Multiple descriptions; the selected detail panel and Database details show them.
A missing description says Function not recorded. No function is inferred from
OCR text or a family prefix. Descriptions are supplied database content and have
not been independently verified. Review/profile entries remain excluded.
Older databases without function columns still load. No database is included
or modified by this patch. Existing GPU and Local contrast processing remain.

### IC Lens 0.5.1 — interface cleanup

Removed Local contrast dropdown, Re-read same snapshot, Auto when steady,
and the Search web button. Local contrast remains the fixed processing mode.
Scans are started manually with Snapshot + scan or Space. The unused live
motion checking loop has also been removed.

Click a recognised marking to open the existing web search in your default
browser (marking plus "IC datasheet"). Selection still fills the marking field
and displays candidate/database information. Automatic result refresh does not
open a browser. Clicking below the list entries does not search; rapid double
clicks on the same name open only one search. Database controls remain available.

### IC Lens 0.5.0 — local database integration

Click Choose component database and select components.sqlite in your separate
Component Database Builder folder. The selection is saved for the next launch.
This patch does not replace or ship a database. If no choice has been saved,
a components.sqlite file beside app.py is loaded when present.

Scan a snapshot. Exact name matches receive a modest ranking boost and a
DB name match label. All existing OCR candidate filters remain unchanged:
unknown parts remain eligible, weak/numeric readings remain accessible through
Show all recognised text. Database membership does not override a low OCR score.
The OCR pass count and processing are unchanged.

Select a candidate, then click Database details / typed lookup to see every
matching source entry, manufacturer/source group, line and package/interface.
You can also type a name and use that button. Multiple manufacturers and package
variants are kept separate. ISP remains an interface, not an inferred package.

Family hints cover LM, 74/54 logic, HCF, AD and selected MCU naming patterns.
They are explicitly labelled pattern only. They do not supply datasheet
functions or prove manufacturer, automotive qualification or chip identity.
Existing OCR family ranking remains in place; this update adds descriptive hints
and exact-database ranking. There are no fuzzy corrections or O/0 substitutions.
Exact matching ignores case and edge whitespace only, using the original OCR
token rather than its punctuation-stripped display key.

After adding sources using the database builder, click Reload database in IC Lens.
This reloads the local catalogue and reranks the existing snapshot results without
rescanning. Database access is read-only and loaded into memory; a database error
does not stop OCR. A failed reload retains the previously loaded snapshot and
shows an error. Startup failures ask you to choose a file again.

Only source_listed entries are loaded. Review entries and generic programmer
profiles cannot generate matches. The initial database's source-quality
limitations still apply: source membership is not independently verified identity.

### IC Lens 0.4.2 — Local contrast only

Every snapshot and re-read now uses Local contrast only. The selector shows
only that treatment, and the preview matches it. CPU and GPU benchmark paths
use the same new scan routine automatically.

Four rotations are retained. Their OCR results also estimate diagonal skew;
if no correction is needed those results are reused, giving four OCR calls
instead of the previous default sixteen. A detected diagonal baseline triggers
four corrected passes (eight total). There are no Original or Lighting correction
OCR passes. Actual latency reduction must be measured on your PC.

Because only one treatment is used, results cannot pass a two-treatment vote.
For this mode, mixed letter/number candidates with an OCR score of at least 0.75
are shown as tentative. PCB reference patterns and numeric-only strings remain
hidden by default. Show all recognised text exposes weaker readings. Rotations
are not counted as independent evidence. The threshold is a starting point, not
a calibrated probability; reducing treatments may miss some faint markings.

### IC Lens 0.4.1 — CUDA loading and fallback hotfix

#### What the supplied diagnostics established

ONNX Runtime 1.22.0 with cuDNN 9.26.0.51 reported it could not locate
cudnn_engines_tensor_ir64_9.dll. All three model sessions then logged a CPU
fallback. The app's cached provider status incorrectly remained CUDA and the
sample test incorrectly passed. The exact missing-file versus missing-dependency
cause is not yet proven. NVIDIA GPU utilization includes other applications.

#### Changes

- Discover installed NVIDIA DLL directories from package file records rather
  than assuming an older wheel directory layout.
- Add those directories to this process's DLL search paths and PATH only.
  No permanent system or user environment changes are made.
- Explicitly load the newer cuDNN tensor-IR DLL, with a useful error if loading
  fails. Keep library and search-directory handles alive.
- Disable ONNX Runtime's internal session.run CPU retry. In the app, the existing
  explicit fallback still works and reports CPU; in strict checks and benchmarks,
  a GPU failure fails the test.
- Refresh and check model session providers after a successful CUDA scan.

### IC Lens 0.4.0 — optional CUDA trial

- Add optional NVIDIA CUDA execution for snapshot OCR with ONNX Runtime GPU 1.22.0 and CUDA/cuDNN pip extras, separate GPU setup/run and forced-CPU launchers, actual sample checks and visible CPU-fallback reasons.
- Add a CPU/CUDA comparison using separate warmed processes and three sample crops; save timing/candidate reports under `%LOCALAPPDATA%\ICLens\benchmarks`. Exclude loading/warm-up from repeated timings.
- Keep rotations, image treatments and candidate rules from 0.3.1. Image enhancement and filtering remain on CPU.
- The 0.4.1 hotfix later established that internal CPU retry could be reported as CUDA in 0.4.0; affected GPU timings are invalid.

### IC Lens 0.3.1 — candidate visibility hotfix

- Change family prefixes from eligibility gates to ranking hints, preserving unfamiliar prefixes and short mixed codes.
- Pool identical text across rotations with at most one vote per treatment. Admit repeated mixed markings at average score >= 0.60 and single-treatment readings at >= 0.90 as tentative; retain PCB/numeric filters.
- Add deduplicated Show all recognised text using computed results. Keep short tokens in raw readings; remove the three-result cap and retain explicit spelling conflicts.
- Compare Original, Local contrast and Lighting correction, plus the selected treatment when different, on the same frozen snapshot; straighten diagonal text before recognition.
- Cover prefix visibility, cross-rotation agreement, short codes and duplicate-vote rules with regressions. Replay saved raw observations from 17 development images; this establishes selection visibility, not improved OCR accuracy.

### IC Lens 0.3 — multi-treatment filtering

- Introduce conservative agreement across treatments, a main-list limit of three, a separate raw/rejected-text window, dominant-baseline straightening and explicit empty/conflicting states.
- Add no online identification service or catalogue download.
- These changes are described under “Changes from 0.2”; 0.3.1 subsequently relaxes filtering and removes the list cap.

### IC Lens 0.2 — frozen-snapshot processing

- Stop live motion from invalidating completed snapshot scans during vibration.
- Add snapshot thumbnail, capture timestamp, reread control and six non-destructive treatments: Original, Local contrast, Lighting correction, Sharpen, Invert and Threshold.
- Preserve original snapshots and existing per-user saved matches; lookup remains unchanged.
