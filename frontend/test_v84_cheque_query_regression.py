from pathlib import Path

SRC = Path(__file__).parent / 'app' / 'services' / 'treasury_service.py'
text = SRC.read_text(encoding='utf-8')


def section(name, next_name=None):
    start = text.index(f'def {name}')
    end = text.index(f'def {next_name}', start) if next_name else len(text)
    return text[start:end]


def test_received_query_does_not_use_payable_note_status_link():
    s = section('get_open_received_cheques', 'get_open_issued_cheques')
    assert 'PayableNoteTransaction' not in s
    assert 'note.[PayableNoteID]' not in s
    assert 'status_link' not in s
    assert 'note.[ReceivableNoteID]' in s


def test_issued_query_binds_status_link_before_where():
    s = section('get_open_issued_cheques', 'get_latest_issued_cheques')
    apply_pos = s.index(') AS status_link')
    where_ref = s.index('status_link.[StatusDocumentID] IS NULL')
    assert apply_pos < where_ref
    assert 'WHERE pnt.[PayableNoteRef] = note.[PayableNoteID]' in s


def test_issued_query_keeps_posted_cheques_out_of_open_set():
    s = section('get_open_issued_cheques', 'get_latest_issued_cheques')
    assert 'note.[State] = 11' in s
    assert 'status_link.[StatusDocumentID] IS NULL' in s
    assert "LIKE N'%وصول چ%'" in s
