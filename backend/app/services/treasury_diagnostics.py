"""عیب‌یابی چک‌های دریافتی: مقایسه با اکسل رسمی راهکاران و ردگیری نگاشت (از treasury_service.py جدا شده)."""

from __future__ import annotations
from decimal import Decimal
from typing import Any
from sqlalchemy import text
from sqlalchemy.engine import Engine
from app.services.received_cheque_current_status import current_received_status_apply
from app.services.treasury_common import (
    _as_datetime,
    _as_jalali_date,
    _as_number,
    _engine,
)


# V122 diagnostic: Excel is validation only; dashboard remains SQL-only.
def compare_received_open_sql_with_rahkaran_excel(excel_bytes: bytes, engine: Engine | None = None) -> dict[str, Any]:
    from io import BytesIO
    from openpyxl import load_workbook

    allowed_statuses = {"نزد بانک", "نزد صندوق", "نزد مأمور وصول", "نزد مامور وصول"}
    def norm(v: Any) -> str:
        if v is None: return ""
        if isinstance(v, float) and v.is_integer(): v = int(v)
        x = str(v).strip().replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ")
        return " ".join(x.split())

    wb = load_workbook(BytesIO(excel_bytes), read_only=True, data_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    try: headers = [norm(x) for x in next(rows)]
    except StopIteration: raise ValueError("فایل Excel خالی است")
    aliases = {"serial":["شماره سریال","سریال","شماره چک"], "sayad":["شماره صیاد","صیاد","شناسه صیاد"], "status":["وضعیت فعلی"], "amount":["مبلغ","مبلغ به ارز عملیاتی"], "due":["تاریخ سررسید"]}
    def col(name):
        for a in aliases[name]:
            if a in headers: return headers.index(a)
        return None
    idx={k:col(k) for k in aliases}
    if idx["status"] is None or idx["amount"] is None: raise ValueError("ستون‌های وضعیت فعلی و مبلغ در Excel پیدا نشد")
    excel_open=[]
    excel_all=[]
    for r in rows:
        status=norm(r[idx["status"]]) if idx["status"] < len(r) else ""
        amount=r[idx["amount"]] if idx["amount"] < len(r) else 0
        try: amount_num=int(Decimal(str(amount or 0)))
        except Exception: amount_num=0
        item={"serial_number":norm(r[idx["serial"]]) if idx["serial"] is not None and idx["serial"] < len(r) else "", "sayad_number":norm(r[idx["sayad"]]) if idx["sayad"] is not None and idx["sayad"] < len(r) else "", "official_status":status.replace("نزد مامور وصول","نزد مأمور وصول"), "amount":amount_num, "due_date_excel":norm(r[idx["due"]]) if idx["due"] is not None and idx["due"] < len(r) else ""}
        excel_all.append(item)
        if status in allowed_statuses:
            excel_open.append(item)

    apply_sql=current_received_status_apply("note", "current_status")
    q=text(f"""
        SELECT note.[ReceivableNoteID] AS [ChequeID], note.[SerialNumber], note.[SayadNumber], note.[Amount], note.[DueDate], note.[State] AS [MasterState],
               current_status.[CurrentChequeState], current_status.[CurrentDocumentItemType], current_status.[CurrentBankAccountRef], current_status.[CurrentStatusDescription],
               current_status.[CurrentStatusDate], current_status.[CurrentStatusDocumentDate], current_status.[CurrentStatusTransactionID]
        FROM RPA3.[ReceivableNote] note
        {apply_sql}
        WHERE note.[NoteType]=1 AND note.[State] IN (1,2) AND note.[NormalORGuarantee]=1
          AND ISNULL(note.[Description],N'') NOT LIKE N'%ضمانت%' AND ISNULL(note.[Description],N'') NOT LIKE N'%تضمین%' AND ISNULL(note.[Description],N'') NOT LIKE N'%حسن انجام%'
        ORDER BY note.[DueDate], note.[ReceivableNoteID]
    """)
    with _engine(engine).connect() as c: sql_rows=c.execute(q).mappings().all()
    def sql_obj(r):
        return {"cheque_id":r["ChequeID"], "serial_number":norm(r["SerialNumber"]), "sayad_number":norm(r["SayadNumber"]), "amount":_as_number(r["Amount"]), "due_date":_as_datetime(r["DueDate"]), "master_state":r["MasterState"], "transaction_state":r["CurrentChequeState"], "document_item_type":r["CurrentDocumentItemType"], "bank_account_ref":r["CurrentBankAccountRef"], "current_description":r["CurrentStatusDescription"], "current_status_date":_as_datetime(r["CurrentStatusDate"]), "current_document_date":_as_datetime(r["CurrentStatusDocumentDate"]), "current_transaction_id":r["CurrentStatusTransactionID"]}
    sql_open=[sql_obj(r) for r in sql_rows]
    by_sayad={}; by_serial_amount={}
    for x in excel_open:
        if x["sayad_number"]: by_sayad.setdefault(x["sayad_number"],[]).append(x)
        if x["serial_number"]: by_serial_amount.setdefault((x["serial_number"],x["amount"]),[]).append(x)
    used=set(); matched=[]; sql_only=[]
    for sr in sql_open:
        cand=by_sayad.get(sr["sayad_number"],[]) if sr["sayad_number"] else []
        if not cand and sr["serial_number"]: cand=by_serial_amount.get((sr["serial_number"],int(sr["amount"] or 0)),[])
        chosen=next((x for x in cand if id(x) not in used),None)
        if chosen: used.add(id(chosen)); matched.append({**sr,"official_status":chosen["official_status"]})
        else: sql_only.append(sr)
    excel_only=[x for x in excel_open if id(x) not in used]

    # V124: annotate SQL-only rows with their status in the *full* official report,
    # even when that status is outside the three approved open holdings.
    all_by_sayad={}
    all_by_serial_amount={}
    for x in excel_all:
        if x["sayad_number"]: all_by_sayad.setdefault(x["sayad_number"], []).append(x)
        if x["serial_number"]: all_by_serial_amount.setdefault((x["serial_number"], x["amount"]), []).append(x)
    for sr in sql_only:
        cand=all_by_sayad.get(sr["sayad_number"], []) if sr["sayad_number"] else []
        if not cand and sr["serial_number"]:
            cand=all_by_serial_amount.get((sr["serial_number"], int(sr["amount"] or 0)), [])
        if cand:
            sr["official_status_any"] = cand[0].get("official_status")
            sr["official_due_date_excel"] = cand[0].get("due_date_excel")
        else:
            sr["official_status_any"] = None
            sr["official_due_date_excel"] = None

    def total(items): return int(sum(Decimal(str(x.get("amount") or 0)) for x in items))
    status_counts={}
    for x in sql_only:
        key=x.get("official_status_any") or "<not-found-in-official-report>"
        status_counts[key]=status_counts.get(key,0)+1
    return {"status":"success", "source":"sql_vs_official_excel_control", "dashboard_source_changed":False, "allowed_official_statuses":["نزد بانک","نزد صندوق","نزد مأمور وصول"], "sql_open":{"count":len(sql_open),"amount":total(sql_open)}, "excel_open":{"count":len(excel_open),"amount":total(excel_open)}, "matched":{"count":len(matched),"amount":total(matched)}, "sql_only":{"count":len(sql_only),"amount":total(sql_only),"official_status_counts":status_counts,"rows":sql_only}, "excel_only":{"count":len(excel_only),"amount":total(excel_only),"rows":excel_only}, "difference":{"count":len(sql_open)-len(excel_open),"amount":total(sql_open)-total(excel_open)}, "note":"V124: sql_only rows are annotated with official_status_any from the full Excel report. Excel remains validation-only and is not a Dashboard source."}


# V123 diagnostic: trace the complete SQL history of every cheque responsible for
# the SQL-vs-official-report discrepancy. Excel remains validation-only.
def analyze_received_cheque_official_discrepancies(excel_bytes: bytes, engine: Engine | None = None) -> dict[str, Any]:
    comparison = compare_received_open_sql_with_rahkaran_excel(excel_bytes, engine=engine)
    sql_only = comparison.get("sql_only", {}).get("rows", [])
    excel_only = comparison.get("excel_only", {}).get("rows", [])

    cheque_ids = {int(x["cheque_id"]) for x in sql_only if x.get("cheque_id") is not None}
    excel_only_resolution = []

    # Resolve the official-report-only rows back to ReceivableNote WITHOUT an
    # open-state filter. This is precisely what lets us see why the 9 collector
    # cheques were missed by State IN (1,2).
    if excel_only:
        clauses = []
        params: dict[str, Any] = {}
        for i, row in enumerate(excel_only):
            sayad = str(row.get("sayad_number") or "").strip()
            serial = str(row.get("serial_number") or "").strip()
            amount = int(row.get("amount") or 0)
            local = []
            if sayad:
                params[f"sayad_{i}"] = sayad
                local.append(f"LTRIM(RTRIM(CAST(note.[SayadNumber] AS nvarchar(100)))) = :sayad_{i}")
            if serial:
                params[f"serial_{i}"] = serial
                params[f"amount_{i}"] = amount
                local.append(f"(LTRIM(RTRIM(CAST(note.[SerialNumber] AS nvarchar(100)))) = :serial_{i} AND note.[Amount] = :amount_{i})")
            if local:
                clauses.append("(" + " OR ".join(local) + ")")
        if clauses:
            q = text(f"""
                SELECT note.[ReceivableNoteID] AS [ChequeID], note.[SerialNumber], note.[SayadNumber],
                       note.[Amount], note.[DueDate], note.[State] AS [MasterState],
                       note.[NormalORGuarantee], note.[Description]
                FROM RPA3.[ReceivableNote] note
                WHERE note.[NoteType] = 1 AND ({' OR '.join(clauses)})
            """)
            with _engine(engine).connect() as c:
                resolved = c.execute(q, params).mappings().all()
            for r in resolved:
                cid = int(r["ChequeID"])
                cheque_ids.add(cid)
                excel_only_resolution.append({
                    "cheque_id": cid,
                    "serial_number": str(r["SerialNumber"] or "").strip(),
                    "sayad_number": str(r["SayadNumber"] or "").strip(),
                    "amount": _as_number(r["Amount"]),
                    "due_date": _as_datetime(r["DueDate"]),
                    "master_state": r["MasterState"],
                    "normal_or_guarantee": r["NormalORGuarantee"],
                    "master_description": r["Description"],
                })

    histories: list[dict[str, Any]] = []
    if cheque_ids:
        ids = sorted(cheque_ids)
        bind = {f"id_{i}": cid for i, cid in enumerate(ids)}
        placeholders = ",".join(f":id_{i}" for i in range(len(ids)))
        q = text(f"""
            SELECT note.[ReceivableNoteID] AS [ChequeID], note.[SerialNumber], note.[SayadNumber],
                   note.[Amount], note.[DueDate], note.[State] AS [MasterState],
                   rnt.[ReceivableNoteTransactionID] AS [TransactionID],
                   rnt.[State] AS [TransactionState], rnt.[DocumentState],
                   rnt.[DocumentItemType], rnt.[BankAccountRef], rnt.[DocumentRef],
                   rnt.[DocumentNumber], rnt.[Date] AS [TransactionDate],
                   rnt.[DocumentDate], rnt.[Description] AS [TransactionDescription]
            FROM RPA3.[ReceivableNote] note
            LEFT JOIN RPA3.[ReceivableNoteTransaction] rnt
              ON rnt.[ReceivableNoteRef] = note.[ReceivableNoteID]
            WHERE note.[ReceivableNoteID] IN ({placeholders})
            ORDER BY note.[ReceivableNoteID], rnt.[Date], rnt.[DocumentDate], rnt.[ReceivableNoteTransactionID]
        """)
        with _engine(engine).connect() as c:
            rows = c.execute(q, bind).mappings().all()
        grouped: dict[int, dict[str, Any]] = {}
        sql_only_ids = {int(x["cheque_id"]) for x in sql_only if x.get("cheque_id") is not None}
        excel_only_ids = {int(x["cheque_id"]) for x in excel_only_resolution}
        for r in rows:
            cid = int(r["ChequeID"])
            item = grouped.setdefault(cid, {
                "cheque_id": cid,
                "side": "sql_only" if cid in sql_only_ids else "excel_only" if cid in excel_only_ids else "resolved",
                "serial_number": str(r["SerialNumber"] or "").strip(),
                "sayad_number": str(r["SayadNumber"] or "").strip(),
                "amount": _as_number(r["Amount"]),
                "due_date": _as_datetime(r["DueDate"]),
                "master_state": r["MasterState"],
                "transactions": [],
            })
            if r["TransactionID"] is not None:
                item["transactions"].append({
                    "transaction_id": r["TransactionID"],
                    "transaction_state": r["TransactionState"],
                    "document_state": r["DocumentState"],
                    "document_item_type": r["DocumentItemType"],
                    "bank_account_ref": r["BankAccountRef"],
                    "document_ref": r["DocumentRef"],
                    "document_number": r["DocumentNumber"],
                    "transaction_date": _as_datetime(r["TransactionDate"]),
                    "document_date": _as_datetime(r["DocumentDate"]),
                    "description": r["TransactionDescription"],
                })
        histories = list(grouped.values())

    # Compact signatures make the common business transition visible without
    # hiding the full history returned above.
    signatures: dict[str, dict[str, int]] = {"sql_only": {}, "excel_only": {}}
    for h in histories:
        side = h["side"]
        if side not in signatures:
            continue
        txs = h["transactions"]
        last = txs[-1] if txs else {}
        key = "master={}|tx={}|doc_item={}|bank={}|desc={}".format(
            h.get("master_state"), last.get("transaction_state"), last.get("document_item_type"),
            "yes" if last.get("bank_account_ref") is not None else "no",
            (str(last.get("description") or "").strip()[:80] or "<empty>")
        )
        signatures[side][key] = signatures[side].get(key, 0) + 1

    unresolved_excel_only = []
    resolved_keys = {(x["serial_number"], x["sayad_number"], int(x["amount"] or 0)) for x in excel_only_resolution}
    for x in excel_only:
        key = (str(x.get("serial_number") or "").strip(), str(x.get("sayad_number") or "").strip(), int(x.get("amount") or 0))
        if key not in resolved_keys:
            unresolved_excel_only.append(x)

    return {
        "status": "success",
        "purpose": "trace_exact_sql_vs_official_status_difference",
        "dashboard_source_changed": False,
        "control": {
            "sql_open": comparison.get("sql_open"),
            "excel_open": comparison.get("excel_open"),
            "sql_only": {"count": len(sql_only), "amount": comparison.get("sql_only", {}).get("amount")},
            "excel_only": {"count": len(excel_only), "amount": comparison.get("excel_only", {}).get("amount")},
            "net_difference": comparison.get("difference"),
        },
        "excel_only_sql_resolution": {
            "requested_count": len(excel_only),
            "resolved_count": len(excel_only_resolution),
            "unresolved_count": len(unresolved_excel_only),
            "resolved_rows": excel_only_resolution,
            "unresolved_rows": unresolved_excel_only,
        },
        "signatures": signatures,
        "history_count": len(histories),
        "histories": histories,
        "next_step": "Use the full histories/signatures to derive the SQL-only business-status rule; do not hard-code cheque IDs.",
    }


def trace_received_cheque_mapping(
    cheque_id: int | None = None,
    serial_number: str | None = None,
    sayad_number: str | None = None,
    document_number: str | None = None,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """Trace one received cheque end-to-end to detect UI/API/SQL mapping mismatches.

    Diagnostic only. It does not change dashboard business rules.
    At least one identifier must be supplied. document_number is matched against
    the approved Receipt linked to the cheque.
    """
    if not any([cheque_id, serial_number, sayad_number, document_number]):
        raise ValueError("حداقل یکی از cheque_id، serial_number، sayad_number یا document_number لازم است")

    where_parts = []
    params: dict[str, Any] = {}
    if cheque_id is not None:
        where_parts.append("note.[ReceivableNoteID] = :cheque_id")
        params["cheque_id"] = cheque_id
    if serial_number:
        where_parts.append("LTRIM(RTRIM(CONVERT(nvarchar(100), note.[SerialNumber]))) = :serial_number")
        params["serial_number"] = str(serial_number).strip()
    if sayad_number:
        where_parts.append("LTRIM(RTRIM(CONVERT(nvarchar(100), note.[SayadNumber]))) = :sayad_number")
        params["sayad_number"] = str(sayad_number).strip()
    if document_number:
        where_parts.append("EXISTS (SELECT 1 FROM RPA3.[ReceiptReceivableNote] rrn INNER JOIN RPA3.[Receipt] r ON r.[ReceiptID]=rrn.[ReceiptRef] WHERE rrn.[ReceivableNoteRef]=note.[ReceivableNoteID] AND CONVERT(nvarchar(100), r.[Number])=:document_number)")
        params["document_number"] = str(document_number).strip()

    query = text(f"""
        SELECT note.[ReceivableNoteID] AS [ChequeID], note.[SerialNumber], note.[Series],
               note.[SayadNumber], note.[Amount], note.[DueDate], note.[State] AS [MasterState],
               note.[NormalORGuarantee], note.[Description], note.[BankRef],
               bank.[Name] AS [BankName], note.[BankBranchName], note.[BankBranchCode],
               note.[CounterPartRef], counterpart.[Code] AS [CounterPartCode],
               counterpart.[Title] AS [CounterPartName]
        FROM RPA3.[ReceivableNote] note
        LEFT JOIN RPA3.[Bank] bank ON bank.[BankID]=note.[BankRef]
        LEFT JOIN FIN3.[DL] counterpart ON counterpart.[DLID]=note.[CounterPartRef]
        WHERE note.[NoteType]=1 AND ({' OR '.join(where_parts)})
        ORDER BY note.[ReceivableNoteID]
    """)

    with _engine(engine).connect() as connection:
        masters = connection.execute(query, params).mappings().all()
        ids = [int(r["ChequeID"]) for r in masters]
        if not ids:
            return {"status": "success", "diagnostic_only": True, "match_count": 0, "matches": [], "warning": "هیچ چکی با شناسه‌های ورودی پیدا نشد"}

        id_params = {f"id{i}": v for i, v in enumerate(ids)}
        placeholders = ",".join(f":id{i}" for i in range(len(ids)))
        tx_rows = connection.execute(text(f"""
            SELECT rnt.[ReceivableNoteRef] AS [ChequeID], rnt.[ReceivableNoteTransactionID] AS [TransactionID],
                   rnt.[State] AS [TransactionState], rnt.[DocumentState], rnt.[DocumentItemType],
                   rnt.[BankAccountRef], rnt.[DocumentRef], rnt.[DocumentNumber], rnt.[Date] AS [TransactionDate],
                   rnt.[DocumentDate], rnt.[Description]
            FROM RPA3.[ReceivableNoteTransaction] rnt
            WHERE rnt.[ReceivableNoteRef] IN ({placeholders})
            ORDER BY rnt.[ReceivableNoteRef], rnt.[Date], rnt.[DocumentDate], rnt.[ReceivableNoteTransactionID]
        """), id_params).mappings().all()
        receipt_rows = connection.execute(text(f"""
            SELECT rrn.[ReceivableNoteRef] AS [ChequeID], r.[ReceiptID], r.[Number] AS [ReceiptNumber],
                   r.[Date] AS [ReceiptDate], r.[ApproveState], r.[Description] AS [ReceiptDescription]
            FROM RPA3.[ReceiptReceivableNote] rrn
            INNER JOIN RPA3.[Receipt] r ON r.[ReceiptID]=rrn.[ReceiptRef]
            WHERE rrn.[ReceivableNoteRef] IN ({placeholders})
            ORDER BY rrn.[ReceivableNoteRef], r.[Date], r.[ReceiptID]
        """), id_params).mappings().all()

    tx_by_id: dict[int, list[dict[str, Any]]] = {i: [] for i in ids}
    for row in tx_rows:
        d = dict(row)
        for key in ("TransactionDate", "DocumentDate"):
            d[key] = _as_datetime(d.get(key))
        tx_by_id[int(row["ChequeID"])].append(d)
    receipts_by_id: dict[int, list[dict[str, Any]]] = {i: [] for i in ids}
    for row in receipt_rows:
        d = dict(row); d["ReceiptDate"] = _as_datetime(d.get("ReceiptDate"))
        receipts_by_id[int(row["ChequeID"])].append(d)

    matches = []
    for row in masters:
        cid = int(row["ChequeID"])
        master = dict(row)
        master["Amount"] = _as_number(master.get("Amount"))
        master["DueDate"] = _as_datetime(master.get("DueDate"))
        master["DueDateJalali"] = _as_jalali_date(row.get("DueDate"))
        txs = tx_by_id[cid]
        latest = txs[-1] if txs else None
        matches.append({
            "cheque_id": cid,
            "sql_master": master,
            "api_expected_core": {
                "cheque_id": cid,
                "serial_number": str(row.get("SerialNumber") or ""),
                "sayad_number": str(row.get("SayadNumber") or ""),
                "amount_rial": _as_number(row.get("Amount")),
                "amount_toman": _as_number(row.get("Amount")) / 10,
                "due_date": _as_datetime(row.get("DueDate")),
                "due_date_jalali": _as_jalali_date(row.get("DueDate")),
                "master_state": row.get("MasterState"),
                "counterparty": row.get("CounterPartName"),
                "bank": row.get("BankName"),
                "bank_branch": row.get("BankBranchName"),
            },
            "latest_transaction_any": latest,
            "transactions": txs,
            "linked_receipts": receipts_by_id[cid],
        })
    return {
        "status": "success", "diagnostic_only": True, "dashboard_source_changed": False,
        "input": {"cheque_id": cheque_id, "serial_number": serial_number, "sayad_number": sayad_number, "document_number": document_number},
        "match_count": len(matches), "multiple_match_warning": len(matches) > 1,
        "matches": matches,
        "check": "Compare sql_master.DueDate/DueDateJalali with api_expected_core and the frontend row. If they differ in UI only, the bug is frontend mapping/merge; if SQL master itself differs, inspect identifier collision or source selection."
    }
