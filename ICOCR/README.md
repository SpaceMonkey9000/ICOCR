# ICOCR 0.8.9.9-RC3

Local IC-marking OCR for microscope camera frames or saved images, with component
catalogue matching and pinout display. Release candidate toward 0.9 beta.

## Windows installation

Install the ICOCR CPU or GPU application installer and the separate ICSuite DATA
installer. Install ICDB if you want to edit the catalogue or pinout library. Install
order does not matter; ICOCR needs DATA before catalogue matching and body detection
are usable. Python is not required for installed builds.

Run the DATA installer as the normal Windows account that will use ICOCR. Its
prepared catalogue already contains generated SVGs; ICDB does not need to be run
first. Close both programs while updating DATA. The data installer preserves an
existing catalogue unless you select database replacement; replacement creates a backup.

## Paths

- Settings: `%LOCALAPPDATA%\ICSuite\ICOCR\settings.json`.
- Shared DATA preference: `%LOCALAPPDATA%\ICSuite\data_location.json`.
- Legacy preference: `%LOCALAPPDATA%\IC_Tools\data_location.json`, read only as fallback.
- Installed DATA default: `%LOCALAPPDATA%\ICSuite\DATA`.
- Source DATA default: sibling `DATA` directory.
- Overrides: `ICLENS_DATA` for DATA; `ICOCR_CONFIG_DIR` for application settings.
- Database: `DATA\db\components.sqlite`; an existing root `components.sqlite` remains supported.
- Models: `DATA\models`, OCR weights under `DATA\models\ocr`.
- Image captures (Space): `Pictures\ICOCR`, using the Windows Pictures folder location.
  Change it in Settings → Database & Documentation → Select image capture folder.
- Rules: `DATA\rules`; bundled defaults under application `factory\rules` seed missing files.

Source execution uses the normal user settings unless `ICOCR_CONFIG_DIR` is set.
For isolated development, set both overrides. Source sibling DATA alone does not
isolate preferences. Changing the shared DATA folder requires restarting ICDB and
ICOCR, and does not move existing files. Image capture folder changes apply
immediately and are remembered; existing captures stay in their original folder.

## First scan

Launch from the Start Menu as your normal user. Select/start the microscope camera
or open an image. Select an IC region and press Scan or Enter. Settings shows the
active DATA location and OCR processor. Recognition and a catalogue match are evidence,
not a guarantee of physical component identity.

## Source execution

Use Python 3.11 64-bit. Run `setup_windows.bat` (CPU) or `setup_windows.bat cuda`, then
`run_windows.bat`. Dependency setup downloads packages. The build kit creates standalone
installers and portable executables. GPU mode falls back to CPU when unavailable.

## Configuration

Application settings, preprocessing, tuning and diagram settings use one settings.json.
Recognition rules use modular JSON under DATA/rules. Use Settings → Rules to enable or
disable modules, save and restart. Legacy per-user config/rules and ranking files are
not automatically migrated. Corrupt settings/rules are reported and use the implemented
fallback defaults; inspect diagnostics before interpreting test results.

The data updater tracks its own managed copies and updates unedited rules/models.
A normal app launch only fills missing factory files and does not replace existing
rules. Edited rules and custom models are preserved by the data updater.

User-guide and troubleshooting files in docs describe feature usage but may still
contain older configuration examples; the paths above are authoritative for this build.
