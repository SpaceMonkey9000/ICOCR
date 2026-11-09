"""Diagnostics window: readings, selection decisions and timings as plain text.

0.8.4.8: the report is built by Tk-free functions and inserted in one call
(it used to be ~60 separate Text.insert calls).
"""
import json
import tkinter as tk
from tkinter import ttk

import multi_chip
from config_loader import configuration_diagnostics


def multi_chip_report(summary, chips):
    lines = ['Multi-chip scan (experimental)',
             f"{summary.get('chips', 0)} chip(s) read, {summary.get('skipped', 0)} over the limit; "
             f"discovery {summary.get('discovery_lines', 0)} line(s) in "
             f"{summary.get('discovery_passes', 0)} OCR pass(es), {summary.get('discovery_ms', 0):.0f} ms; "
             f"total {summary.get('total_ms', 0):.0f} ms",
             f"Detector: {summary.get('detector', '—')}"]
    for chip in chips:
        lines.append(f"\nChip {chip.get('number')}: {multi_chip.label_for(chip)} [{chip.get('status')}] "
                     f"source {chip.get('source')}, region {chip.get('region')}, body "
                     f"{chip.get('body_status')}, {chip.get('elapsed', 0):.2f} s")
        if chip.get('error'):
            lines.append(f"  Error: {chip['error']}")
        lines.append('  Discovery text: ' + ' | '.join(d['text'] for d in chip.get('discovery', [])))
        for candidate in (chip.get('scan_result') or {}).get('all_candidates', []):
            lines.append(f"  {candidate['text']}: {candidate.get('selection_decision', 'unknown')} | "
                         f"{candidate.get('selection_reason') or candidate.get('rejection_reason') or 'eligible'} | "
                         f"OCR {candidate.get('score', 0):.3f}")
        for raw in (chip.get('diagnostics') or {}).get('raw', []):
            lines.append(f"  raw {raw['rotation']:3}° | {raw['score']:.2f} | {raw['text']}")
    return '\n'.join(lines) + '\n\n'


def candidate_report(row):
    lines = [f"{row['text']}: {row.get('selection_decision', 'unknown')} | "
             f"{row.get('selection_reason') or row.get('rejection_reason') or 'eligible'} | "
             f"OCR {row.get('score', 0):.3f} | support {row.get('support', 1)} | "
             f"rank {row.get('selection_rank', row.get('rank', 0)):.3f}"]
    if row.get('applied_rules'):
        lines.append('  Applied rules: ' + json.dumps(row['applied_rules'], ensure_ascii=False))
    if row.get('join_evidence'):
        lines.append('  Wrapped-line observations: ' + json.dumps(row['join_evidence'], ensure_ascii=False))
    if row.get('whitespace_joined'):
        lines.append(f"  Printed line: {row.get('raw_text', row['text'])}")
    correction = row.get('ocr_correction')
    if correction:
        lines.append(f"  OCR correction: {correction['observed']} -> {correction['part']}; "
                     f"character {correction['index']+1}: {correction['from_char']} -> {correction['to_char']}; "
                     f"heuristic cost {correction['cost']:.2f}")
    return '\n'.join(lines) + '\n'


def diagnostics_report(diagnostics, scan_result, performance, evidence, vote, configuration):
    """Full Diagnostics text (wording and order as in 0.8.4.7)."""
    out = ['Configuration (startup snapshot):\n' + json.dumps(configuration, indent=2) + '\n\n',
           'Current recognition evidence:\n' + evidence + '\n\n',
           'Scan errors:\n' + str(diagnostics.get('error', '')) + '\n\n']
    if diagnostics.get('multi_chip'):
        out.append(multi_chip_report(diagnostics['multi_chip'], diagnostics.get('multi_chips', [])))
    out.append(f"Selected rotation: {diagnostics.get('selected_rotation', '—')}°\n")
    out.append('Scores are OCR engine scores, not calibrated identity probabilities.\n\n')
    for row in diagnostics.get('raw', []):
        out.append(f"{row['rotation']:3}° | {row['mode']:20} | {row['score']:.2f} | {row['text']}\n")
    for key, title in (('preprocessing', 'Preprocessing policy and attempts'),
                       ('live_observation', 'Observation Live')):
        if diagnostics.get(key):
            out.append(f'\n{title}:\n' + json.dumps(diagnostics[key], indent=2) + '\n')
    timings = diagnostics.get('timings', {})
    out.append('\nStage timings (ms):\n')
    for key in ('total_ms', 'body_detection_ms', 'preprocessing_ms', 'matching_ms'):
        out.append(f"{key}: {timings.get(key, 0):.2f}\n")
    for stage in timings.get('ocr_passes', []):
        out.append(f"OCR {stage['rotation']}° {stage['treatment']} "
                   f"deskew={stage['deskew']}: {stage['milliseconds']:.2f}\n")
    for key, value in performance.items():
        out.append(f'{key} (latest): {value:.2f}\n')
    if hasattr(performance, 'summaries'):
        out.append('\nRolling samples (up to 240): count | median | p95\n')
        for key, count, median, p95 in performance.summaries():
            out.append(f'{key}: {count} | {median:.2f} | {p95:.2f}\n')
    if diagnostics.get('scan_input'):
        out.append('\nActual scan input: ' + json.dumps(diagnostics['scan_input'], ensure_ascii=False) + '\n')
    body = diagnostics.get('body_detection', {})
    if body:
        out.append(f"\nBody crop: {body.get('status')} — {body.get('reason')}\n")
        out.append(f"Heuristic score: {body.get('score', 0):.3f} (not a probability)\n")
        for reason, count in body.get('rejections', {}).items():
            out.append(f"Rejected contours: {reason} = {count}\n")
    if vote is not None:
        out.append(f"\nLive frame vote: {vote.summary()} | reads {vote.reads}, misses {vote.misses}\n")
        for key, count in vote.tally():
            out.append(f"  {key}: {count}\n")
    scan_mode = 'fast (0°/90° detection)' if diagnostics.get('fast') else 'full 4-rotation'
    out.append(f"\nScan mode: {scan_mode}; OCR passes {diagnostics.get('ocr_calls', '—')}\n")
    scan_result = scan_result or {}
    ranking = scan_result.get('line_ranking')
    if ranking:
        block = ranking.get('block', {})
        out.append(f"\nLine ranking {ranking.get('version')} (weights {ranking.get('weights_version')}): "
                   f"{block.get('lines', 0)} line(s) in the marking block"
                   + (f"; new choice {ranking['abstained']} withheld (score below threshold)"
                      if ranking.get('abstained') else '') + '\n')
    out.append('\nSelection decisions:\n')
    out.extend(candidate_report(row) for row in scan_result.get('all_candidates', []))
    return ''.join(out)


class DiagnosticsMixin:
    def show_diagnostics(self):
        win = tk.Toplevel(self.root)
        win.title('OCR diagnostics — readings, selection and timings')
        win.geometry('850x520')
        ttk.Label(win, text='Copy text manually if needed. Rejected text can include valid short markings.',
                  padding=8).pack(fill='x')
        box = tk.Text(win, wrap='none')
        scrollbar = ttk.Scrollbar(win, command=box.yview)
        scrollbar.pack(side='right', fill='y')
        box.pack(fill='both', expand=True)
        box.configure(yscrollcommand=scrollbar.set)
        box.insert('end', diagnostics_report(self.diagnostics, self.scan_result, self.performance,
                                             self.recognition_evidence, self.vote,
                                             configuration_diagnostics()))
        box.configure(state='disabled')
