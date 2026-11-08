"""Background loading and activation of the component catalogue."""
import logging
import queue
import threading
from pathlib import Path

from component_catalog import Catalog
from project_paths import DATA
from scan_result import build_scan_result

from shared_data import database_file
DATABASE = database_file(DATA)


class DatabaseMixin:
    def load_database_startup(self):
        if DATABASE.is_file():
            self.install_database(DATABASE)
        else:
            self.database_state.set('No components.sqlite in DATA. Open ICDB to set up the catalogue, '
                                    'then Reload database.')

    def install_database(self, path, on_success=None, failure_title=None, failure_prefix=''):
        """Read and index the catalogue on a worker thread (0.8.3.2).

        Large databases took seconds on the Tk thread at startup and on Reload.
        The previously loaded catalogue stays active until the new one is ready;
        scans started meanwhile use the previous one (or none at startup).
        """
        self.database_request += 1
        request = self.database_request
        keep = ' — previous database stays active until it is ready' if self.catalog is not None else ''
        self.database_state.set(f'Loading {Path(path).name}…{keep}')

        def stale():
            return request != self.database_request or self.closing.is_set()

        def work():
            # 0.8.4.3: a load superseded by a later Load/Reload (or by closing)
            # stops before reading and drops its catalogue instead of queueing it.
            if stale():
                return
            try:
                result, error = Catalog(path), None
            except Exception as exc:
                logging.exception('Database load failed: %s', path)
                result, error = None, exc
            if stale():
                logging.info('Database load superseded; discarded %s', path)
                return
            self.database_results.put((request, result, error, on_success, failure_title, failure_prefix))
        threading.Thread(target=work, name='database-load', daemon=True).start()

    def accept_database(self):
        while True:
            try:
                request, new_catalog, error, on_success, title, prefix = self.database_results.get_nowait()
            except queue.Empty:
                return
            if request != self.database_request:
                continue  # a later Load/Reload superseded this one
            if error is not None:
                if self.catalog is not None:
                    self.database_state.set(self.database_summary(self.catalog) + ' (new database not loaded)')
                else:
                    self.database_state.set('Database unavailable — choose a file. '+str(error))
                if title:
                    self.show_dialog('showerror', title, prefix+str(error))
                continue
            self.activate_database(new_catalog)
            if on_success is not None:
                try:
                    on_success()
                except Exception as exc:
                    logging.exception('Database load follow-up failed')
                    self.show_dialog('showerror', 'Database', str(exc))

    @staticmethod
    def database_summary(catalog):
        return f'{catalog.path.name}: {catalog.count:,} distinct names loaded'

    def activate_database(self, new_catalog):
        self.invalidate('Database changed — reading again')
        self.catalog = new_catalog
        self.database_path = str(new_catalog.path)
        if self.diagram_panel is not None:
            self.diagram_panel.library.refresh()
        self.database_state.set(self.database_summary(new_catalog))
        self.scan_result = build_scan_result(self.filtered_rows,
            self.diagnostics.get('all_candidates', self.filtered_rows), self.catalog)
        self.refresh_readings()

    def reload_database(self):
        self.install_database(DATABASE, failure_title='Reload failed',
                              failure_prefix='Check components.sqlite in the shared DATA folder.\n')
