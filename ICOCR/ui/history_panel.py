"""History tab: this session's readings, their pinouts and the ICDB hand-off."""
import webbrowser
from urllib.parse import quote_plus
from PySide6.QtWidgets import (QFileDialog, QMessageBox, QLineEdit, QInputDialog)
from component_catalog import describe
from logic_diagrams import reference_labels
from package_pinouts import select_reference
from project_paths import DATA
from qt_icdb_bridge import icdb_entry, launch_icdb
from ui.app_paths import APP_ROOT


class HistoryMixin:
    """Session history, its pinout and Open in / Add to ICDB. Mixed into MainWindow."""

    def _history_pinout_for(self, entry):
        """Resolve all linked references for one history entry; do not affect Identify."""
        row = entry['row']
        match = row.get('selected_database_match') or {}
        self.history_reference_choices = []
        self.history_reference_select.blockSignals(True)
        self.history_reference_select.clear()
        self.history_reference_select.setEnabled(False)
        self._history_pinout_source = None
        self.history_pinout_image.set_source(None)
        self.history_pinout_note.clear()
        self.history_pinout_title.setText('Pinout — ' + str(match.get('part') or row.get('key') or 'Unknown'))
        if not match or not self.library:
            self.history_pinout_note.setText('No linked ICDB pinout')
            self.history_reference_select.blockSignals(False)
            return
        try:
            choices = self.library.choices(row)
            self.history_reference_choices = choices
            self.history_reference_select.addItems(reference_labels(choices))
            self.history_reference_select.setEnabled(bool(choices))
            remembered_id = entry.get('history_pinout_reference_id')
            selected, report = select_reference(choices, match.get('package', ''),
                                                remembered_id, None)
            self.history_pinout_note.setText(report.get('reason', ''))
            if selected:
                self.history_reference_select.setCurrentIndex(choices.index(selected))
            else:
                self.history_reference_select.setCurrentIndex(-1)
        except Exception as exc:
            self.history_pinout_note.setText('Pinout lookup error: ' + str(exc))
        finally:
            self.history_reference_select.blockSignals(False)
        self._render_history_reference(self.history_reference_select.currentIndex())

    def _history_reference_chosen(self, index):
        """Remember the manual package choice only for the selected history entry."""
        history_index = self.history_list.currentRow()
        if not (0 <= history_index < len(self.history_model.entries)
                and 0 <= index < len(self.history_reference_choices)):
            return
        entry = self.history_model.entries[history_index]
        entry['history_pinout_reference_id'] = self.history_reference_choices[index].get('reference_id')
        self.history_pinout_note.setText('Manual reference selection for this history entry')
        self._render_history_reference(index)

    def _render_history_reference(self, index):
        """Render the chosen ICDB reference with the shared theme-aware loader."""
        self._history_pinout_source = None
        self.history_pinout_image.set_source(None)
        if not 0 <= index < len(self.history_reference_choices):
            self.history_pinout_note.setText('No linked ICDB pinout')
            return
        try:
            self._history_pinout_source = self._reference_pixmap(
                self.history_reference_choices[index]['path'])
            self._fit_history_pinout_pixmap()
        except Exception as exc:
            self.history_pinout_note.setText('Cannot render pinout: ' + str(exc))

    def _fit_history_pinout_pixmap(self):
        if self._history_pinout_source is not None:
            self.history_pinout_image.set_source(self._history_pinout_source)

    # -- history ---------------------------------------------------------------
    def _refresh_history(self):
        previous = self.history_list.currentRow()
        self.history_list.blockSignals(True)
        self.history_list.clear()
        for entry in self.history_model.entries:
            row = entry['row']
            self.history_list.addItem(f"{entry['time']}  {row.get('text') or row.get('key')} — "
                                      f"{row.get('function_summary') or 'No database match'}")
        self.history_list.blockSignals(False)
        self.tabs.setTabText(self.history_tab_index, f'History ({len(self.history_model.entries)})')
        if 0 <= previous < len(self.history_model.entries):
            self.history_list.setCurrentRow(previous)
            self._history_selected(previous)
        else:
            self._history_selected(-1)

    def _history_selected(self, index):
        self.history_datasheet_btn.setEnabled(0 <= index < len(self.history_model.entries) and bool(self._history_part_number(index)))
        self.history_open_icdb_btn.setEnabled(bool(self._history_matched_part(index)))
        self.history_add_icdb_btn.setEnabled(0 <= index < len(self.history_model.entries))
        self.history_alias_btn.setEnabled(0 <= index < len(self.history_model.entries))
        if not 0 <= index < len(self.history_model.entries):
            self.history_details.clear()
            self._history_pinout_source = None
            self.history_pinout_title.setText('Pinout')
            self.history_reference_choices = []
            self.history_reference_select.blockSignals(True)
            self.history_reference_select.clear()
            self.history_reference_select.setEnabled(False)
            self.history_reference_select.blockSignals(False)
            self.history_pinout_image.set_source(None)
            self.history_pinout_note.setText('Select a history entry to view its pinout')
            return
        entry = self.history_model.entries[index]
        row = entry['row']
        self.history_details.setPlainText(
            f"{row.get('text') or row.get('key')} — first seen {entry['time']}\n\n"
            + (f"Corrected alias: {row['ocr_correction']['corrected_text']} → "
               f"{row['resolved_partnumber']}\n\n" if (row.get('selected_database_match') or {}).get('match_type') == 'corrected_alias' else '')
            + describe(row.get('database_matches', [])))
        self._history_pinout_for(entry)

    def _history_matched_part(self, index):
        """Use a confirmed database selection, never an unmatched OCR string."""
        if not 0 <= index < len(self.history_model.entries):
            return ''
        match = self.history_model.entries[index]['row'].get('selected_database_match') or {}
        return str(match.get('part') or '').strip()

    def _open_history_in_icdb(self):
        part = self._history_matched_part(self.history_list.currentRow())
        if part:
            self._send_history_to_icdb(part, 'open')

    def _add_history_to_icdb(self):
        index = self.history_list.currentRow()
        if not 0 <= index < len(self.history_model.entries):
            return
        # OCR markings are not necessarily manufacturer part numbers. Require the
        # operator to verify or correct the value before preparing an ICDB draft.
        proposed = self._history_part_number(index)
        part, accepted = QInputDialog.getText(self, 'Add to ICDB',
            'Part number (verify OCR marking):', QLineEdit.EchoMode.Normal, proposed)
        if accepted and part.strip():
            self._send_history_to_icdb(part.strip(), 'add')

    def _add_history_alias(self):
        index = self.history_list.currentRow()
        if 0 <= index < len(self.history_model.entries):
            row = self.history_model.entries[index]['row']
            correction = row.get('ocr_correction') if (row.get('selected_database_match') or {}).get('match_type') == 'corrected_alias' else {}
            marking = str(correction.get('corrected_text') or row.get('raw_text')
                          or row.get('text') or row.get('key') or '').strip()
            if marking:
                self._send_history_to_icdb(marking, 'alias', row.get('selected_database_match'))

    def _send_history_to_icdb(self, part, action, target=None):
        prefs = self.preferences.load()
        folder = APP_ROOT.parent / 'ICDB' if action == 'alias' else prefs.get('icdb_installation', '')
        try:
            folder = icdb_entry(folder) if folder else None
        except (ValueError, OSError):
            folder = None
        if folder is None:
            candidates = [APP_ROOT.parent / 'ICDB_0.8.6_PySide6_Components_Pinouts',
                          APP_ROOT.parent / 'ICDB',
                          APP_ROOT]
            for candidate in candidates:
                try:
                    folder = icdb_entry(candidate)
                    break
                except (ValueError, OSError):
                    continue
        if folder is None:
            selected = QFileDialog.getExistingDirectory(
                self, 'Locate ICDB installation (contains icdb_qt.py)',
                str(APP_ROOT.parent))
            if not selected:
                return
            try:
                folder = icdb_entry(selected)
            except (ValueError, OSError) as exc:
                QMessageBox.warning(self, 'ICDB', str(exc))
                return
        try:
            process = (launch_icdb(folder, DATA, part, action=action, target=target) if action == 'alias'
                       else launch_icdb(folder, DATA, part, action=action))
            if action == 'alias':
                self._watch_alias_save(process)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'ICDB', f'Failed to launch ICDB:\n{exc}')
            return
        self.icdb_installation = str(folder)
        try:
            updated = self.preferences.load()
            updated['icdb_installation'] = self.icdb_installation
            self.preferences.save(updated)
        except OSError:
            pass
        self.statusBar().showMessage(f'{"Adding" if action == "add" else "Opening"} {part} in ICDB')

    def _watch_alias_save(self, process):
        from PySide6.QtCore import QTimer
        from shared_data import database_file
        from pathlib import Path
        db = database_file(DATA)
        paths = (db, Path(str(db) + '-wal'))

        def stamp():
            values = []
            for path in paths:
                try:
                    values.append(path.stat().st_mtime_ns)
                except FileNotFoundError:
                    values.append(None)
            return tuple(values)

        current = stamp()
        def check():
            nonlocal current
            if self._closing:
                return
            updated = stamp()
            if updated != current and not self.database_loader.isRunning():
                current = updated
                self._refresh_alias_results = True
                self.reload_database()
            if process.poll() is None or updated != current:
                QTimer.singleShot(800, check)
        QTimer.singleShot(800, check)

    def _history_part_number(self, index):
        if not 0 <= index < len(self.history_model.entries):
            return ''
        row = self.history_model.entries[index]['row']
        match = row.get('selected_database_match') or {}
        return str(match.get('part') or row.get('key') or row.get('text') or '').strip()

    def _search_history_datasheet(self):
        part = self._history_part_number(self.history_list.currentRow())
        if part:
            webbrowser.open('https://www.google.com/search?q=' + quote_plus(part + ' ic datasheet'))

    def _clear_history(self):
        self.history_model.clear()
        self._refresh_history()
        self.history_details.clear()
