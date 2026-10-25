from app.services.treasury_service import get_open_issued_cheques, _issued_posting_status, _master_cheque_payload


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _Connection:
    def __init__(self, rows, queries):
        self._rows = rows
        self._queries = queries

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query):
        self._queries.append(str(query))
        return _Result(self._rows)


class _Engine:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def connect(self):
        return _Connection(self.rows, self.queries)


def _row(cheque_id: int, amount: int):
    return {
        "ChequeID": cheque_id,
        "ChequeState": 11,
        "Amount": amount,
        "DueDate": None,
        "DaysUntilDue": None,
        "SerialNumber": None,
        "Series": None,
        "SayadNumber": None,
        "AccountNumber": None,
        "BankRef": None,
        "BankName": None,
        "BankBranchName": None,
        "BankBranchCode": None,
        "CounterPartRef": None,
        "CounterPartCode": None,
        "CounterPartName": None,
        "AccountRef": None,
        "CurrencyRef": 1,
        "NormalORGuarantee": 1,
        "Description": None,
        "DocumentID": None,
        "DocumentNumber": None,
        "DocumentDate": None,
    }


def test_open_issued_cheques_uses_active_master_notes_without_row_limit(monkeypatch):
    monkeypatch.setattr("app.services.treasury_service._karamad_cheques", lambda _kind: [])
    engine = _Engine([_row(1, 100), _row(2, 250)])
    result = get_open_issued_cheques(engine=engine)

    assert result["state_filter"] == [11]
    assert result["paid_state_excluded"] == 28
    assert result["row_limit"] is None
    assert result["returned_count"] == 2
    assert result["returned_total_amount"] == 350
    assert "note.[State] = 11" in engine.queries[0]
    assert not engine.queries[0].lstrip().startswith("SELECT TOP (")


def test_issued_state_11_is_open_unposted_and_28_is_posted(monkeypatch):
    monkeypatch.setattr(
        "app.services.treasury_service.settings.treasury_issued_paid_states",
        "28",
    )
    assert _issued_posting_status(11) == (False, "باز / سند نخورده")
    assert _issued_posting_status(28) == (True, "سند خورده / برداشت‌شده")

    open_payload = _master_cheque_payload(_row(10, 500), "issued")
    assert open_payload["is_posted"] is False
    assert open_payload["cashflow_open"] is True
    assert open_payload["state_label"] == "باز / سند نخورده"

    paid_row = _row(11, 700)
    paid_row["ChequeState"] = 28
    paid_payload = _master_cheque_payload(paid_row, "issued")
    assert paid_payload["is_posted"] is True
    assert paid_payload["cashflow_open"] is False
    assert paid_payload["state_label"] == "سند خورده / برداشت‌شده"


def test_issued_cheque_posted_by_status_document_description():
    from app.services.treasury_service import _issued_posting_status

    posted, label = _issued_posting_status(
        11,
        "تعيين وضعيت چک عادي عهده ما, وصول چ ش؛/0140/431868 ؛تاريخ1404/11/24",
    )
    assert posted is True
    assert "سند خورده" in label


def test_open_issued_query_treats_approved_duration_change_as_posted(monkeypatch):
    # Rahkaran posts a paid cheque with an approved DurationChange (long-term to current,
    # credited to the bank). The line text is blank and State stays 11, so the keyword
    # check alone left ~6,000 paid cheques looking open on the dashboard.
    monkeypatch.setattr("app.services.treasury_service._karamad_cheques", lambda _kind: [])
    engine = _Engine([])
    get_open_issued_cheques(engine=engine)
    sql = engine.queries[0]

    assert "RPA3.[DurationChangePayableNote] AS dcp" in sql
    assert "dcp.[PayableNoteRef] = note.[PayableNoteID]" in sql
    assert "dc.[ApproveState] = 3" in sql
    assert "CAST(dcp.[DueDate] AS date) = CAST(note.[DueDate] AS date)" in sql
    assert "status_link.[StatusDocumentID] IS NULL" in sql


def test_latest_issued_queries_use_duration_change_status_link():
    from app.services.treasury_service import get_latest_issued_cheques

    engine = _Engine([])
    get_latest_issued_cheques(engine=engine)

    # primary query plus the master-table fallback (primary returned no rows)
    assert len(engine.queries) == 2
    for sql in engine.queries:
        assert "RPA3.[DurationChange] AS dc" in sql
        assert "dcp.[PayableNoteRef] = master_note.[PayableNoteID]" in sql


def test_duration_change_status_document_is_posted_whatever_its_header_text():
    for header in ("تغییر مدت به روز - وصول چک", "تغییر مدت به روز - کارمزد بانکی", "تغییر مدت به روز"):
        assert _issued_posting_status(11, header) == (True, "سند خورده / برداشت‌شده")
    assert _issued_posting_status(11, "پرداخت 40% پ ف 601") == (False, "باز / سند نخورده")


def test_cashflow_forecast_excludes_duration_change_posted_cheques():
    from pathlib import Path

    source = (Path(__file__).parent / "app" / "services" / "finance_prediction_service.py").read_text(encoding="utf-8")
    issued = source[source.index("issued_query = text("):source.index("received_query = text(")]
    assert "RPA3.[DurationChangePayableNote] AS dcp" in issued
    assert "dc.[ApproveState] = 3" in issued


def test_issued_queries_exclude_shareholder_counterpart(monkeypatch):
    # Shareholder cheques often read «پرداخت به جاری شرکا ...», so the description filter
    # alone let them through; the «سهامداران» counterpart must be excluded as well.
    from app.services.treasury_service import SHAREHOLDERS_DL_CODE, get_latest_issued_cheques

    monkeypatch.setattr("app.services.treasury_service._karamad_cheques", lambda _kind: [])
    engine = _Engine([])
    get_open_issued_cheques(engine=engine)
    get_latest_issued_cheques(engine=engine)

    assert SHAREHOLDERS_DL_CODE == "950031"
    assert len(engine.queries) == 3
    for sql in engine.queries:
        assert "ISNULL(counterpart.[Code], N'') <> N'950031'" in sql


def test_cashflow_forecast_excludes_shareholder_cheques():
    from pathlib import Path

    source = (Path(__file__).parent / "app" / "services" / "finance_prediction_service.py").read_text(encoding="utf-8")
    issued = source[source.index("issued_query = text("):source.index("received_query = text(")]
    assert "shareholder.[Code] = :shareholders_dl_code" in issued
    assert '"shareholders_dl_code": SHAREHOLDERS_DL_CODE' in source
