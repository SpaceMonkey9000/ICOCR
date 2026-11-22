"""ICOCR (PySide6) entry point: python qt_full.py

Prepares configuration, logging and the shared DATA lease before any
recognition module is imported, and keeps start-up failures visible.
"""
import os
from pathlib import Path
import sys
import traceback


def main():
    root = Path(__file__).resolve().parent.parent
    os.environ['ICLENS_DATA'] = str(root / 'DATA')
    os.environ['ICOCR_RULES_DIR'] = str(root / 'DATA' / 'rules')
    os.environ['ICOCR_CONFIG_DIR'] = str(root / 'prototype-config')
    from PySide6.QtWidgets import QApplication, QMessageBox
    app = QApplication(sys.argv)  # noqa: F841  (must stay alive until exit)
    lease = None
    try:
        from project_paths import DATA
        from data_lock import DataLease
        # Shared with ICDB; refused while DATA is being updated. Taken before
        # anything below writes into DATA (rule seeds, folders, log).
        lease = DataLease(DATA)
        from user_paths import prepare_config
        # Seeds settings and rule files on a fresh installation. Must run before
        # config_loader (imported by every recognition module) takes its snapshot.
        prepare_config(DATA)
        from app_state import prepare_data_folder, configure_logging
        prepare_data_folder()
        configure_logging()
        import qt_window
    except Exception as exc:
        report = traceback.format_exc()
        try:
            from user_paths import CONFIG_DIR
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            (CONFIG_DIR/'startup-error.log').write_text(report, 'utf-8')
            report += '\nLog: ' + str(CONFIG_DIR/'startup-error.log')
        except Exception:
            pass
        QMessageBox.critical(None, 'ICOCR startup failed',
                             str(exc) if isinstance(exc, RuntimeError) else report)
        if lease is not None:
            lease.close()
        return 1
    try:
        return qt_window.run()
    finally:
        lease.close()


if __name__ == '__main__':
    sys.exit(main())
