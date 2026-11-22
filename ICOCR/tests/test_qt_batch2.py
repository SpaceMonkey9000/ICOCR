import tempfile
import unittest
from pathlib import Path
from qt_session_history import ReadingHistory
from qt_user_preferences import Preferences

class HistoryTest(unittest.TestCase):
    def test_dedup_and_upgrade(self):
        history = ReadingHistory()
        assert history.add([dict(key='ABC123', score=.7)], False)
        assert not history.add([dict(key='abc123', score=.8)], False)
        assert history.add([dict(key='ABC123', trusted_database_matches=[{'match_type':'exact'}])], True)
        assert len(history.entries) == 1
        assert history.entries[0]['database_loaded']
        history.clear()
        assert len(history.entries) == 0

    def test_explicit_choice_is_added_and_updates_existing_history(self):
        history = ReadingHistory()
        history.add([dict(key='ABC123', score=.7)], True)
        self.assertTrue(history.add_selected(dict(key='ABC123', text='ABC123', score=.5), True))
        self.assertEqual(len(history.entries), 1)
        self.assertTrue(history.entries[0]['row']['manually_selected'])
        self.assertEqual(history.entries[0]['row']['score'], .5)
        self.assertTrue(history.add_selected(dict(key='XYZ12', score=.8), False))
        self.assertEqual(len(history.entries), 2)
        self.assertTrue(history.entries[1]['manually_selected'])

    def test_prefs_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefs = Preferences(Path(tmp)/'qt_preferences.json')
            assert prefs.load() == {}
            prefs.save({'peaking_enabled': True, 'camera_mode': '1920x1080 @30'})
            assert prefs.load()['peaking_enabled'] is True
            assert not (Path(tmp)/'qt_preferences.json.tmp').exists()

if __name__ == '__main__':
    unittest.main()
