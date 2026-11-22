# ICOCR user guide

## Camera and images

The camera starts when the window opens. Choose another camera in the header and
press **Start**; **Stop** releases it. **Open image** works the same way on a saved
photo, and **Image folder** opens the folder where captures are saved.

Below the picture:

- **Capture** (Space) saves the full-resolution frame.
- **Scan** (Enter) reads the selected region.
- **Freeze** holds the current frame. A frozen frame and an opened image are shown at
  full resolution; live video is shown at preview resolution. Scans and captures
  always use the full-resolution frame.
- **Focus peaking** highlights sharp detail on the preview only.
- **Fit** shows the whole frame and keeps fitting it when the window is resized.

The mouse wheel zooms and a middle-button drag moves the picture. F11 toggles full
screen and Escape leaves it.

## Scanning

Select one chip: drag a rectangle over it, or click the outline of a detected chip,
which selects it with a margin and scans it at once. Right-click restores the default
region. Include the whole marking but as little other board text as possible.

Press **Scan** or Enter. A scan requested while another is running starts as soon as
that one finishes.

The readings appear under **Recognised markings**, the automatic choice first.

- **Click** a reading to show its component, pinout and, under **Identification
  details**, the evidence for it.
- **Double-click** a reading to choose it yourself. It moves to the top with a check
  mark and is added to History. A new scan clears the choice.
- **Search datasheet** opens a web search for the part number (or the marking)
  plus "ic datasheet".

After a scan the selected marking (solid) and the chip body (dashed) are outlined
with a label. On live video the outlines follow the board as it moves or rotates,
and come back when the scanned area returns to view. They can be switched off in
Settings → Recognition.

### Live recognition

With **Live recognition** on, the selected region is scanned about every 1.6 seconds
while the camera runs. The previous outlines stay until a new result replaces them.
**Sleep live OCR when the scene is unchanged** pauses live scanning after the set idle
time; the preview keeps running and scanning resumes when the picture changes.

## Pinout

The pinout of the selected reading is shown from ICDB. When ICDB has several pinouts
for a part, for example for different packages, choose one in the list above the
diagram. Wheel zooms, drag pans and double-click fits. Pinouts are read-only here;
edit them in ICDB.

## History

The History tab lists this session's readings: every automatic choice from a scan and
every reading you chose by double-clicking. It is cleared when ICOCR closes.

Select an entry to see its pinout; its package choice is kept separately from the
Identify tab. The buttons:

- **Search datasheet** searches for the entry's part number.
- **Open in ICDB** opens ICDB with the matched part selected.
- **Add to ICDB** opens ICDB with a new component staged for this marking. Check the
  part number before saving it in ICDB.
- **Clear history** empties the list.

The first time, ICOCR asks for the ICDB folder and remembers it.

## Diagnostics

The Diagnostics tab shows the full details of the last scan: OCR lines, candidates,
rejected readings and the rules involved. Include it when reporting a wrong reading.

## Settings

| Tab | Contents |
| --- | --- |
| Camera settings | Video mode, capture back end (DirectShow or Media Foundation), focus-peaking colour, sensitivity and opacity. Applies when the camera next starts. |
| Recognition | Scan mode (single or multiple chips), live recognition and sleep, body detection, fast scan, package classification, excluded readings and the on-picture outlines |
| Rules | Turn recognition rule modules on or off; see [RULES.md](RULES.md) |
| Data and documentation | Shared DATA folder, saved photos folder, models folder, package model and body segmentation model |
| Tools | Theme (Light or Dark graphite), invert pinouts in dark mode, the active OCR processor, **Reload database** and **Open data folder** |

A new DATA folder must already contain a database. Changing it needs a restart of
ICOCR and ICDB, and existing files are not moved.

After saving changes in ICDB, use **Reload database** to see them.
