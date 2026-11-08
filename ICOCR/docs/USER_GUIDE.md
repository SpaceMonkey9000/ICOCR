# User guide

## Capture and scanning

The camera starts once after the startup device search. Select a camera,
DirectShow or Media Foundation backend, and resolution/frame rate. Stop/Start
applies camera changes. Request MJPG changes the requested camera
format; hardware support varies. Open image provides the same selection and
scanning workflow without a live camera.

Drag over one chip. Right-click restores the default selection box. Scan or Enter reads the current selection. Space (or Capture image) saves the full current frame as a JPEG (quality 95) in `DATA/captures`, one image per key press. Live recognition
waits for a stable scene, scans, then tracks a selected or provisional marking.
Line rereads vote across frames. Unresolved targets get initial rapid retries,
then retry every five seconds. Text agreement is not proof of component identity.
F11 toggles fullscreen; Escape exits fullscreen.

## Scan options

| Control | Behaviour |
| --- | --- |
| Fast scan | Detects text at 0/90 degrees and reads each detected line both ways. Enabled by default. |
| Fast scan off | Uses the four-rotation path, with deskew where applicable. |
| Auto body crop (experimental) | Uses geometric body location by default. An unsuccessful body scan gets one full-selection recovery scan. |
| Chip detector (test) | Displays trained model outlines. Click a detected chip to select it. Does not by itself enable detector-based cropping. |
| Body from chip detector (test) | Uses the selected trained model for cropping when Auto body crop is enabled and the body is eligible. |
| Detector model | Loads an ONNX model, with an adjacent JSON specification where supplied; applies to both outline display and OCR cropping. |

A clipped or unsuitable detector body falls back to the full selection. Body
outlines are experimental, especially on near-square packages. Keep the selection
relevant to the intended chip: a recovery scan also sees surrounding PCB text.
The release does not infer pin functions or identify package types.

## Multi-chip scan (experimental, 0.8.3.7)

Settings → Recognition → **Multi-chip scan (experimental)**. Off by default and
saved with the other settings. When on, Scan / Enter reads every chip in the
selection instead of one: drag around the chips you want (or the whole view)
and press Enter. Each chip gets a numbered outline and label on the video, and
one line in Recognised markings (`Chip 2: ★ JA1044V — …`).

- Chips are found by their printed marking: a line with letters and digits,
  four or more characters, that is not a board label (R45, IC3) or resistor code.
  With **Body from chip detector** on, the trained detector's bodies are added.
- Each chip is read with the normal single-chip pipeline and your current
  settings (fast scan, body crop, Original fallback, snapshot preprocessing).
  The other chips' text is painted over in its region first.
- ★ automatic pick, ✓ technician choice, grey = unconfirmed (no automatic pick,
  e.g. a chip cut by the frame edge). Click a line to search it; Edit reading
  corrects the selected chip.
- Outlines follow camera movement and hide when the view changes too much.
  A new selection or any setting change clears them.
- Live recognition stays single-chip: Live is paused while this is on.
  Clicking a chip's reading logs that chip (its region as the snapshot).
- Time grows with the number of chips (about 1-4 s per chip on CPU, plus about
  1.5 s to find them); at most 10 chips are read per scan.

Any part-like printed text counts, so inductor or module markings appear as
chips too. As always, a reading is not an identification.

## Results and database

Load database opens the SQLite catalogue created by the separate Component
Database Builder. ICOCR expects its `components`, `entries`, and `sources`
tables; an arbitrary CSV or SQLite schema cannot be loaded directly. Import CSV
through the database builder. Reload database refreshes the read-only snapshot
after changes in that application.

Exact names take priority. Partial matching permits at most three additional
characters on either side; it does not substitute OCR characters to force a match.
Multiple matches/descriptions are represented by one selected description and
an asterisk. Database lookup shows details.

Weak or conflicting results can remain provisional while live rereads collect
more evidence. Short mixed markings need body evidence to become provisional
without a database match. Short numeric resistor-like text and PCB reference
labels remain filtered; four-digit IC-body markings have separate evidence rules.

Show all recognised text and Diagnostics expose rejected candidates, readings,
matching decisions, body location and timing information. The normal list prefers
database matches when present. Clicking a result or history item opens a web
search and records the click. Datasheet opens a saved URL when available, otherwise
a search. OCR itself runs locally; these explicit searches use the browser.

Saved matches and Save / edit match maintain personal marking notes separately
from the component database. They do not modify the catalogue.

## Logging clicked readings (0.8.3.8)

**Log clicked readings** (Settings → Database & Documentation, on by default, remembered) saves a
record only when you click a reading or use Edit reading. The click is your
confirmation that the text is right. Scans you do not click are not saved.

Each confirmation saves, in `%LOCALAPPDATA%\ICLens\confirmed`:

- `C_000123.jpg`: the scan snapshot (the selection; in multi-chip mode the
  chip's region), JPEG quality 95, without overlays.
- One row in `confirmed.csv` (opens in Excel; close it there before the next
  click, or that row is not written and the status bar says so):

| Column | Meaning |
| --- | --- |
| `part_number` | Database part number when the reading matched, else the confirmed text. |
| `confirmed_text` | The text you clicked or typed. |
| `database_match` | yes / no. |
| `corrected` | no = you clicked the automatic pick (★); yes = you picked another line or edited the text. |
| `correction` | accepted automatic pick, picked another line, chosen; no automatic pick, or edited text. |
| `ocr_text` | What the OCR read (for an edit: the reading you corrected). |
| `automatic_pick`, `all_readings` | The ★ pick and every reading of that scan, for checking and for training better line selection later. |
| `mode`, `chip`, `scan` | scan / live / multi-chip, chip number, and a scan id. Several clicks on one scan give several rows; the last row of a scan is the final answer. |

The same reading is saved once per scan. Old `scan_logs` folders from 0.8.3 to
0.8.3.7 are left untouched.

## User data

Open data folder opens `%LOCALAPPDATA%\ICLens` on Windows. On platforms without
LOCALAPPDATA, the fallback is `~/ICLens`.

| Item | Purpose |
| --- | --- |
| `matches.json` | Known markings saved by releases before 0.8.4.8 (still used to rank OCR candidates). |
| `database_path.json` | Last selected catalogue path. |
| `marking_clicks.csv` | Clicked marking and database-match status. |
| `confirmed/` | Confirmed readings: JPEG snapshots and `confirmed.csv` (0.8.3.8). |
| `ICOCR.log` | Application and worker error log. |
| `benchmarks/` | Reports produced by the CPU/GPU benchmark tool. |

Session history is in memory, not a persistent inventory. Not every interface
option is persisted across runs. Old per-release click logs can still be migrated
on first use when no current click log exists.

## 0.8.2.2 experiment controls

**Targeted treatment fallback** searches the alternate treatment on both axes
when selection fails or a strong identifier conflict remains. Standard scans
start with Original, then try Local contrast when this fallback is needed. It can increase scan
time. Off restores the preceding retry policy.

**Detector alignment corrections** matches the native detector resize method.
As of 0.8.2.5, video always uses the newest camera frame with either setting.
Version 0.8.2.6 projects recent body and text outlines in a background worker,
including translation and rotation. Unreliable motion or expired results hide
the outlines; movement alone no longer hides them. Off selects the older resize method.
Both controls default on and can be tested independently. The supplied rotated
body model is installed in models; body-from-detector cropping remains opt-in.

Background body detection pauses while OCR is busy. An inference already in
flight is allowed to finish. Body results are shared with OCR for up to 0.75 s
on stationary views, with refresh after motion, resize, or preprocessing changes.
Diagnostics include preview_fps (rendered updates, not camera capture FPS),
ui_tick_ms, overlay_motion_ms, detector_ms, body_cache_hit and body_cache_age_ms.
Timing diagnostics include rolling median and p95 over up to 240 samples,
in addition to latest values. Samples are operation-based, not whole-session
averages. overlay_motion_ms measures the background worker; it is no longer UI
processing time. OCR detection/recognition breakdown is available in fast mode.

## Recovery and live latency in 0.8.2.6

When tracking fails, Live enters **Reacquiring IC** for up to 0.75 seconds.
It retains the prior reading and searches the selected square for the recent
marking appearance. Two new matching frames are required to restore tracking.
An ambiguous match, changed selection, different frame size or expired grace
period returns to normal acquisition. The positional label is hidden while
its location is unverified. This recovery searches translation at the current
scale; large rotation, zoom and severe motion blur can still require fresh OCR.

Successful recovery retains the existing reading vote and database result.
Diagnostics show recovery_count, recovery_ms, recovery_search_ms and
full_scan_requests. recovered appearance is not new OCR evidence.

Live scans complete their initial orientation search (unless the existing
confident-result early exit applies). Optional additional treatment/deskew
passes stop at inference boundaries after an 800 ms elapsed-time budget.
This is not an 800 ms limit on the complete scan: an individual model call or
the initial search can take longer. With Targeted treatment fallback enabled, later
unresolved live attempts alternate Local contrast and Original as their first
treatment. Frozen scans retain the original retry search. Superseded/lost live
acquisitions stop between model calls, then wait for a stable view.

## External rules (0.8.3.9)

Marking rules and ranking settings live under `config/` beside `app.py`.
See [the configuration guide](../config/README.md) for file contents, editing
examples, validation and migration from older brand/weight files. Restart after
editing. Run `run_windows.bat config-check` before scanning; malformed files fall
back individually to bundled defaults and trigger a startup warning.

OCR diagnostics include per-file status and hashes of the active external
configuration. Camera, detector, preprocessing and other GUI preferences are
not moved by this release.


## 0.8.5 defaults and labels

Sleep defaults to 120 seconds without scene movement. Recognition and detector
work pause; the camera preview and previous pinout remain visible. Movement or
a manual action wakes recognition and invalidates the previous scene. A saved
custom timeout is retained.

Clicked readings are labelled **Selected**; manually edited readings are
**Clarified**. Confirmation logs record the user's choice, not independently
verified component identity. Existing saved preprocessing policies are retained;
Standard uses Original first. New application logs use `DATA/ICOCR.log`.
