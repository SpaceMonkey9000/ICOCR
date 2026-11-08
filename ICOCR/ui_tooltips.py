"""Control help kept alongside the UI, including shortcuts and data ownership."""
from tkinter import TclError
from ui_regions import Tooltip

HELP = {
    'Capture device': 'Capture starts automatically after the startup camera search. Choose another device, then Stop and Start to switch.',
    'Refresh': 'Search for connected cameras. Refresh does not restart capture.',
    'Start': 'Start the selected camera using the backend, resolution and FPS in Settings.',
    'Stop': 'Stop camera capture. A pending automatic startup is cancelled.',
    'Settings': 'Camera, recognition, database, documentation and diagnostic settings.',
    'Open image': 'Stop the camera and load a still image for scanning.',
    'Scan [Enter]': 'Scan the selected region. Drag on the preview to select a region; right-click to restore the default box. Enter scans; Space saves a clean image.',
    'Live recognition': 'Automatically read a stable view and track the result. Motion wakes recognition from sleep. Multi-chip mode pauses Live recognition.',
    'Capture image [Space]': 'Save the full camera frame without overlays to DATA/captures. Space saves once per key press.',
    'Open image folder': 'Open DATA/captures, containing clean full-frame images.',
    'Recognised markings': 'Click a reading to mark it Selected and search it. Edited text is Clarified. With logging enabled, clicked and edited readings are saved as confirmations; this is not independent identity verification.',
    'Edit reading… (correct the text, then search)': 'Correct the printed marking, mark it Clarified and search for a datasheet. Logging also saves the corrected text and snapshot.',
    'Sleep after inactivity': 'Pause recognition and detector work after no scene movement. Default: 120 seconds. The camera preview and previous pinout remain visible. Movement or a manual action wakes recognition.',
    'Capture backend': 'Camera driver API. Apply changes by stopping and starting capture.',
    'Requested resolution / FPS': 'Requested camera mode. Actual resolution and frame rate depend on the device. Restart capture to apply.',
    'Request MJPG': 'Request MJPG camera transport. Availability depends on the capture device; restart capture to apply.',
    'Import / select chip-body model…': 'Select an ONNX chip detector. Models are stored in DATA/models; OCR text models are separate.',
    'OCR input region': 'Read the full selection or crop the IC body geometrically or with the trained model. Failed body scans can retry the full selection.',
    'Fast scan (0°/90° detection)': 'Use two text-detection orientations with recognition of opposite reading directions. Original is the default first treatment.',
    'Targeted treatment fallback': 'When the standard scan has no selected identifier or conflicting readings, retry both text axes with the alternate treatment: Local contrast after Original, or Original after Local contrast.',
    'Scan verification': 'Check uncertain Live readings across frames. OCR scores are not calibrated identity probabilities.',
    'Observation Live (prototype)': 'Experimental Live scheduling and observation selection. Applies only while Live recognition is enabled.',
    'Multi-chip scan (experimental): read every chip in the selection': 'Scan multiple chips from one frozen frame with Enter or Scan. Live recognition pauses while this mode is enabled.',
    'Snapshot preprocessing…': 'Choose a snapshot preprocessing policy. Standard starts with Original. Explicit saved single/fallback policies remain in effect. This editor does not change Live preprocessing.',
    'Detector alignment corrections': 'Apply alignment corrections to trained detector crops. This can add processing time.',
    'Show all recognised text': 'Include excluded and lower-priority OCR text in the readings list.',
    'Show pinout / reference': 'Display the database pinout or reference for the selected part. Sleep retains the last displayed reference.',
    'Log clicked readings': 'Save clicked or clarified readings with their snapshot to DATA/confirmed, plus confirmation metadata. Automatic recognition alone does not confirm a reading.',
    'Choose DATA folder…': 'Choose the shared ICSuite folder containing the component database, models, pinouts, captures and logs.',
    'Reload database': 'Reload the component catalogue from the current DATA folder.',
    'Open data folder': 'Open the shared DATA folder. New application diagnostic messages are written to ICOCR.log; old ic_lens.log files are retained.',
    'Refresh pinout references': 'Reload the pinout/reference index after changes to the shared database or reference images.',
    'Open confirmed folder': 'Open the saved confirmation snapshots and confirmed.csv.',
    'Open configuration folder': 'Open per-user configuration and UI preferences in the ICOCR AppData folder on Windows.',
    'Diagnostics': 'Inspect OCR timings, runtime providers, recognised text and scan evidence.',
}


def install_control_help(root):
    """Add help by control caption without replacing existing event bindings."""
    for widget in root.winfo_children():
        try:
            text = widget.cget('text')
        except TclError:
            text = None
        if text in HELP:
            Tooltip(widget, HELP[text])
        install_control_help(widget)
