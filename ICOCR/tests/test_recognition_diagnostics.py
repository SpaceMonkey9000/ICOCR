import json
from recognition_diagnostics import begin, end, event, report
from ocr_core import line_tokens


def test_trace_records_rejected_short_token():
    token, events = begin()
    try:
        rows = line_tokens('LVC573A X', .99, 0, 'Original', None)
        assert [r['key'] for r in rows] == ['LVC573A']
    finally:
        end(token)
    assert any(e.get('key') == 'X' and not e['accepted'] for e in events)
    event('outside_scan')
    assert not any(e['stage'] == 'outside_scan' for e in events)


def test_report_keeps_evidence_not_configuration_payload():
    row = dict(key='TE04502', score=.996, selection_reason='unverified')
    cfg = dict(modular_rules=dict(modules=[dict(name='Join',enabled=True,config={'secret_payload': 1}),dict(name='Other',enabled=False)]))
    result = report(dict(selected=row,all_candidates=[row],configuration=cfg),dict(raw=[{'text':'TE04502'}]))
    assert result['summary']['identification_status']=='unverified'
    assert result['summary']['ocr_confidence']==.996
    assert result['enabled_rules']==['Join']
    assert 'secret_payload' not in json.dumps(result)
    assert result['pipeline']['raw_ocr_readings'][0]['text']=='TE04502'


def test_disabled_trace_does_not_record_or_leak():
    from recognition_diagnostics import active
    assert not active()
    line_tokens('74HC08D X', .99, 0, 'Original', None)
    assert not active()
    token, events = begin()
    try:
        line_tokens('74HC08D X', .99, 0, 'Original', None)
        assert any(e.get('key') == '74HC08D' for e in events)
    finally:
        end(token)
    count = len(events)
    line_tokens('UN0413E X', .99, 0, 'Original', None)
    assert len(events) == count
