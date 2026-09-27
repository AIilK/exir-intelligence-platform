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
