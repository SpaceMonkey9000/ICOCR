"""Body-only OCR retry using synthetic detector and recognizer results."""
import sqlite3
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from body_locator import body_crop
from body_scan import read_with_body
from component_catalog import Catalog
from ocr_core import OCR, straighten, unstraighten_box
from recognition_diagnostics import begin, end


BODY = [[35, 45], [160, 45], [160, 140], [35, 140]]
LOT = [[65, 65], [125, 90], [121, 100], [61, 75]]
PART = [[60, 103], [132, 103], [132, 116], [60, 116]]
PCB = [[165, 85], [192, 85], [192, 100], [165, 100]]


def test_body_only_recovery_deskews_and_ignores_off_body_database_match(tmp_path):
    path = tmp_path / 'parts.sqlite'
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE components(id INTEGER PRIMARY KEY, part_number TEXT,
                manufacturer TEXT, family_hint TEXT, function TEXT);
            CREATE TABLE entries(id INTEGER PRIMARY KEY, component_id INTEGER, source_id INTEGER,
                status TEXT, line INTEGER, package_or_interface TEXT, qualifiers TEXT, function TEXT);
            CREATE TABLE sources(id INTEGER PRIMARY KEY, name TEXT);
            INSERT INTO components VALUES (1, 'TPIC2810', 'TI', '', ''),
                                          (2, 'LM2904', 'TI', '', '');
        """)
    catalog = Catalog(path)
    image = np.zeros((190, 200, 3), np.uint8)
    body = dict(status='detected', source='model', box=BODY, milliseconds=0.)
    masked, offset = body_crop(image, body)
    skew = np.degrees(np.arctan2(25, 60))
    straight, matrix = straighten(image, skew, return_matrix=True)
    deskewed_part = unstraighten_box(PART, matrix)

    class SimulatedOCR(OCR):
        def __init__(self):
            self.fast = True
            self.first_marking = self.recovery_marking = '46AX70T'
            self.can_deskew = True
            self.engine = SimpleNamespace(text_score=.5)
            self.runtime = {'device': 'cpu'}

        def _probe(self, crop, treatment, scale):
            return crop

        def _detect_turn(self, image, k, cache=None):
            lines = []
            if k == 0:
                if image.shape == masked.shape:
                    lines = [(self.first_marking, (np.asarray(LOT) - offset).tolist(), .97)]
                elif image.shape == straight.shape and self.can_deskew:
                    lines = [('TP1C2810', deskewed_part, .91)]
                elif image.shape == self.original_shape:
                    lines = [(self.recovery_marking, LOT, .97), ('LM2904', PCB, .99)]
            return (None, None, lines, (), ()), 0., False

        def _line_readings(self, boxes, crops, origin, k, threshold):
            return [dict(text=text, box=box, score=score, rotation=0, alternative=False, crop_id=i)
                    for i, (text, box, score) in enumerate(boxes)], 0

    engine = SimulatedOCR()
    engine.original_shape = image.shape
    token, events = begin()
    try:
        with patch.dict('os.environ', {'ICOCR_DEFER_BODY_RETRY': '1', 'ICOCR_STRAIGHTEN_FALLBACK': '1'}):
            read_with_body(engine, image, enabled=True, detection=body, body_only=True, catalog=catalog)
    finally:
        end(token)
    diagnostics = engine.last_diagnostics
    selected = diagnostics['scan_result']['selected']
    assert selected['key'] == 'TP1C2810'
    assert selected['selected_database_match']['part'] == 'TPIC2810'
    assert selected['selected_database_match']['match_type'] == 'corrected'
    np.testing.assert_allclose(selected['box'], PART)
    assert selected['body_box'] == BODY
    assert diagnostics['body_detection']['status'] == 'applied'
    assert diagnostics['body_recovery']['recovered']
    assert {'LM2904'} <= {e['text'] for e in events if e['stage'] == 'outside_body_rejected'}
    assert 'LM2904' not in {r['key'] for r in diagnostics['scan_result']['all_candidates']}

    with patch.dict('os.environ', {'ICOCR_DEFER_BODY_RETRY': '1', 'ICOCR_STRAIGHTEN_FALLBACK': '1'}):
        read_with_body(engine, image, enabled=True, detection=body, catalog=catalog)
    assert engine.last_diagnostics['scan_result']['selected']['key'] == 'LM2904'

    engine.first_marking = 'TPIC2810'
    read_with_body(engine, image, enabled=True, detection=body, body_only=True, catalog=catalog)
    assert engine.last_diagnostics['scan_result']['selected']['key'] == 'TPIC2810'
    assert 'body_recovery' not in engine.last_diagnostics
    assert engine.last_diagnostics['ocr_calls'] == 2

    engine.first_marking = engine.recovery_marking = 'TP1C28'
    previous = dict(selected, box=LOT)
    with patch.dict('os.environ', {'ICOCR_STRAIGHTEN_FALLBACK': '1'}):
        read_with_body(engine, image, enabled=True, detection=body, body_only=True,
                       previous_rows=[previous], catalog=catalog)
    assert engine.last_diagnostics['scan_result']['selected']['key'] == 'TP1C2810'
    assert engine.last_diagnostics['straightened_fallback']
    assert engine.last_diagnostics['live_prefix']['retained'] is False

    engine.can_deskew = False
    for holds in (1, 2):
        read_with_body(engine, image, enabled=True, detection=body, body_only=True,
                       previous_rows=[previous], catalog=catalog)
        assert engine.last_diagnostics['scan_result']['selected']['key'] == 'TP1C28'
        previous = engine.last_diagnostics['retained_live_reading']
        assert previous['live_prefix_holds'] == holds
        assert previous['selected_database_match']['part'] == 'TPIC2810'
    read_with_body(engine, image, enabled=True, detection=body, body_only=True,
                   previous_rows=[previous], catalog=catalog)
    assert 'retained_live_reading' not in engine.last_diagnostics
    assert engine.last_diagnostics['live_prefix']['retained'] is False

    engine.first_marking = 'LM2904'
    read_with_body(engine, image, enabled=True, detection=body, body_only=True,
                   previous_rows=[previous], catalog=catalog)
    assert engine.last_diagnostics['scan_result']['selected']['key'] == 'LM2904'
    assert 'live_prefix' not in engine.last_diagnostics
