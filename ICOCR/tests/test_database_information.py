import sqlite3
from contextlib import closing

from ui.settings_dialog import database_information


def test_database_information_matches_icdb_counts(tmp_path):
    path = tmp_path / 'components.sqlite'
    with closing(sqlite3.connect(path)) as db:
        db.executescript("""
            CREATE TABLE components(part_number TEXT, manufacturer TEXT);
            INSERT INTO components VALUES ('A', 'Maker 1'), ('A', 'Maker 2');
            CREATE TABLE pl_definitions(id INTEGER PRIMARY KEY);
            INSERT INTO pl_definitions VALUES (1);
            CREATE TABLE icdb_database_version(id INTEGER PRIMARY KEY, base TEXT, revision INTEGER);
            INSERT INTO icdb_database_version VALUES (1, '2026.11', 12);
        """)
    assert database_information(path) == ('2026.11-r12', '2', '1')


def test_database_information_handles_missing_and_legacy_databases(tmp_path):
    path = tmp_path / 'components.sqlite'
    assert database_information(path) == ('Unavailable',) * 3
    assert not path.exists()
    with closing(sqlite3.connect(path)) as db:
        db.execute('CREATE TABLE components(part_number TEXT)')
    assert database_information(path) == ('Unversioned', '0', 'Unavailable')
