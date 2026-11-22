# ICOCR 0.9.0-beta.1

ICOCR reads the markings on integrated circuits from a microscope camera or a saved
image, matches them against the ICDB component catalogue and shows the matching
pinout. It runs locally; no images leave the computer.

A reading and a catalogue match are evidence, not proof of a component's identity.

This is a beta. Please report problems together with the version in the window title
and the log file (see below).

## Install and start (Windows)

**Installer or portable build:** run the installer, or extract the portable zip and
start `ICOCR.exe`. No Python is needed.

**From source:**

1. Install Python 3.11 (64-bit) with the Python Launcher. Python 3.13 is not
   supported.
2. Run `setup_qt_windows.bat` (CPU) or `setup_qt_windows.bat cuda` (NVIDIA GPU).
3. Start with `run_qt_windows.bat` or `run_qt_windows.bat cuda`.

The camera starts automatically when the window opens.

## Using ICOCR

1. Choose a camera, or use **Open image** for a saved photo.
2. Drag a rectangle over one chip, or click a detected chip outline. Right-click
   restores the default region.
3. Press **Scan** (or Enter). The readings appear under *Recognised markings*, the
   automatic choice first.
4. Click a reading to see its pinout and the evidence for it. Double-click it to
   choose it yourself; it moves to the top and is added to History.

**Capture** (Space) saves the full-resolution frame. **Freeze** holds the frame for
zooming and scanning. The **History** tab keeps this session's readings and can open
or add them in ICDB. See [docs/USER_GUIDE.md](docs/USER_GUIDE.md) for everything else.

## Where things are kept

| What | Where |
| --- | --- |
| Shared DATA folder | `ICLENS_DATA` if set; else the folder saved in Settings; else `%LOCALAPPDATA%\ICSuite\DATA` (installed) or a `DATA` folder next to the ICOCR folder (source) |
| Component database (from ICDB) | `DATA\db\components.sqlite` |
| Recognition rules | `DATA\rules` |
| Models chosen in Settings | `DATA\models` |
| Log | `DATA\ICOCR.log` |
| Window preferences | `DATA\qt_preferences.json` |
| Settings and rule seed | `%LOCALAPPDATA%\ICSuite\ICOCR` (`ICOCR_CONFIG_DIR` overrides) |
| Start-up error report | `%LOCALAPPDATA%\ICSuite\ICOCR\startup-error.log` |
| Captures | `Pictures\ICOCR`, or the folder set in Settings |
| Bundled models | `models\` in the application folder |

`ICLENS_DEVICE=cpu|cuda|auto` chooses the OCR processor (default `auto`).

## Documentation

- [docs/USER_GUIDE.md](docs/USER_GUIDE.md): camera, scanning, History and Settings
- [docs/RULES.md](docs/RULES.md): recognition rule modules and how to add rules
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md): setup, GPU, camera and recognition problems
- [docs/DEVELOPER.md](docs/DEVELOPER.md): code layout, tests, the DATA contract with ICDB and design decisions
- [CHANGELOG.md](CHANGELOG.md): changes per release

## Intentionally left out

These features were in earlier builds and were left out of the Qt application on
purpose:

- **Multi-frame voting and verification of live readings.** In testing it lowered the
  rate of correct identifications, so live recognition is a periodic full scan of
  the selected region instead.
- **The trained chip detector** from earlier builds. Chip bodies are found by the
  bundled segmentation model, with a geometric fallback.
- **Preprocessing and tuning editors.** Tuning values are read from the settings
  folder's configuration files.
- **The confirmed-reading CSV and JPEG record.** History is kept for the session only.

## Known issues in this beta

- **Open in ICDB** and **Add to ICDB** start ICDB from its source folder
  (`.venv-qt`). They do not yet find an installed `ICDB.exe`.
- Body detection (the **Prototype: OCR only inside detected IC bodies** option) is
  experimental.
