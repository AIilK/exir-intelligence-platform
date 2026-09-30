"""Section 1 of the liquidity dashboard: open received cheques, «قطعی» and «اتکا».

Definitions agreed with management:
- قطعی  = 100% of the nominal amount of open cheques due inside the horizon (all clear);
- اتکا  = each cheque × its ``recommended_reliance_percent``: the customer's history
          (``CustomerChequeBehaviorEngine``) plus the cheque rules (``cheque_reliance_rules``).
- overdue open cheques get their own card and are NOT in the horizon totals;
- open returned cheques are an information card only;
- customer history counts every collected (3,30,32,33) / returned (4,10,17,26) state.

Rahkaran uses the existing open portfolio and reliance (``cheque_return_predictions``).
Karamad applies the same engine and cheque rules to its own history (``tblChequeD``):
open = StatusRef 1 غیرقطعی / 2 نزد صندوق / 3 واگذار شده (in bank).  Karamad never marks a
banked cheque collected, so a «واگذار شده» cheque more than 30 days past due without being
returned counts as collected (same rule as ``customer_cheque_return_risk``).

A Rahkaran cheque from a hybrid branch («هیبرید …») pays the company for stock: it is the
hybrid settlement, shown on its own and eliminated from the group total, like the cash
section.  Channels: B2B = Rahkaran, هیبرید = Karamad.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Callable

from sqlalchemy import text

from app.services.customer_cheque_behavior_engine import CustomerChequeBehaviorEngine
from app.services.liquidity.account_map import is_hybrid_counterpart
from app.services.liquidity.cash_movements import CHANNEL_LABELS, CHANNEL_SYSTEMS, SYSTEM_CHANNEL, SalesChannel
from app.utils.jalali import format_jalali_date

CACHE_TTL_SECONDS = 300
ALLOWED_TERM_DAYS = 90
KARAMAD_BANKED_COLLECTED_AFTER_DAYS = 30
MAX_CUSTOMERS = 300

HOLDING_LABELS = {"cashbox": "نزد صندوق", "bank": "نزد بانک", "collector": "نزد مأمور وصول", "pending": "غیرقطعی (کارآمد)"}
RAHKARAN_HOLDING = {"نزد صندوق": "cashbox", "نزد بانک": "bank", "نزد مأمور وصول": "collector"}

KARAMAD_OPEN = {1: "pending", 2: "cashbox", 3: "bank"}
KARAMAD_COLLECTED = {4}
KARAMAD_RETURNED = {6, 7, 8, 9, 10}      # history: returned at some point (8 = returned then collected)
KARAMAD_RETURNED_OPEN = {6, 7, 10}       # returned and not settled yet
RAHKARAN_RETURNED_OPEN_STATES = (4, 17)  # واخواست شده، حقوقی شده (not yet settled)

RELIANCE_BANDS = {"high": (80.0, None), "medium": (50.0, 80.0), "low": (None, 50.0)}
OVERDUE_AGE_BUCKETS = ((1, 30, "تا ۳۰ روز"), (31, 90, "۳۱ تا ۹۰ روز"), (91, None, "بیش از ۹۰ روز"))

KARAMAD_CHEQUES_SQL = text("""
    SELECT c.[inx] AS [ChequeID], c.[Price] AS [Amount], c.[DueDate],
           COALESCE(c.[ReceiptDate], c.[BookDate]) AS [ReceiptDate], c.[StatusRef], c.[Serial],
           c.[DLRef] AS [CustomerRef], CAST(dl.[Code] AS nvarchar(50)) AS [CustomerCode], dl.[Name] AS [CustomerName],
           c.[BranchRef], br.[Name] AS [BranchName], v.[Name] AS [VisitorName], sl.[Name] AS [SLName]
    FROM dbo.[tblChequeD] AS c
    LEFT JOIN dbo.[tblDL] AS dl ON dl.[ID] = c.[DLRef]
    LEFT JOIN dbo.[tblSL] AS sl ON sl.[ID] = c.[SLRef]
    LEFT JOIN dbo.[tblBranch] AS br ON br.[ID] = c.[BranchRef]
    LEFT JOIN dbo.[tblFactorF] AS f ON f.[ID] = c.[FactorRef]
    LEFT JOIN dbo.[tblVisitor] AS v ON v.[ID] = f.[VisitorRef]
    WHERE c.[DueDate] IS NOT NULL AND c.[DLRef] IS NOT NULL
""")

RAHKARAN_RETURNED_OPEN_SQL = text(f"""
    SELECT note.[ReceivableNoteID] AS [ChequeID], note.[Amount], note.[DueDate], note.[State],
           counterpart.[Title] AS [CustomerName]
    FROM RPA3.[ReceivableNote] AS note
    LEFT JOIN FIN3.[DL] AS counterpart ON counterpart.[DLID] = note.[CounterPartRef]
    WHERE note.[NoteType] = 1 AND note.[NormalORGuarantee] = 1
      AND note.[State] IN ({", ".join(str(s) for s in RAHKARAN_RETURNED_OPEN_STATES)})
""")


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value:
        return date.fromisoformat(str(value)[:10])
    return None


def _code(value: Any) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value[:-2] if text_value.endswith(".0") else text_value or None


def _round(value: float) -> float:
    return round(float(value), 2)


def fetch_rahkaran_predictions() -> list[dict[str, Any]]:
    from app.services.finance_prediction_service import FinancePredictionService
    report = FinancePredictionService().cheque_return_predictions(limit=None, include_all_open=True)
    return report.get("cheques") or []


def fetch_rahkaran_returned_open() -> list[dict[str, Any]]:
    from app.database.sqlserver import get_sqlserver_engine
    with get_sqlserver_engine().connect() as connection:
        return [dict(r) for r in connection.execute(RAHKARAN_RETURNED_OPEN_SQL).mappings()]


def fetch_karamad_cheques() -> list[dict[str, Any]]:
    from app.database.karamad_sqlserver import get_karamad_sqlserver_engine
    with get_karamad_sqlserver_engine().connect() as connection:
        return [dict(r) for r in connection.execute(KARAMAD_CHEQUES_SQL).mappings()]


Fetcher = Callable[[], list[dict[str, Any]]]
DEFAULT_FETCHERS: dict[str, Fetcher] = {
    "rahkaran": fetch_rahkaran_predictions,
    "rahkaran_returned": fetch_rahkaran_returned_open,
    "karamad": fetch_karamad_cheques,
}

_cache: dict[tuple[str, date], tuple[float, Any]] = {}
_cache_lock = threading.Lock()


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _public(cheque: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in cheque.items() if not k.startswith("_")}


class ReceivedChequeService:
    def __init__(self, today: date | None = None, fetchers: dict[str, Fetcher] | None = None,
                 cache_ttl_seconds: int = CACHE_TTL_SECONDS):
        self.today = today or date.today()
        self.fetchers = {**DEFAULT_FETCHERS, **(fetchers or {})}
        self.cache_ttl_seconds = cache_ttl_seconds

    def _cached(self, name: str, loader: Callable[[], Any], refresh: bool) -> Any:
        key = (name, self.today)
        now = time.monotonic()
        with _cache_lock:
            hit = _cache.get(key)
            if hit and not refresh and now - hit[0] < self.cache_ttl_seconds:
                return hit[1]
        value = loader()
        with _cache_lock:
            _cache[key] = (now, value)
        return value

    # -- Rahkaran -------------------------------------------------------------

    def _rahkaran(self, refresh: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        predictions = self._cached("rahkaran", self.fetchers["rahkaran"], refresh)
        cheques = []
        for p in predictions:
            due = _as_date(p.get("due_date"))
            if due is None:
                continue
            name = p.get("counterpart_name") or "مشتری نامشخص"
            amount = float(p.get("amount") or 0)
            reliance = float(p.get("recommended_reliance_percent") or 0)
            breakdown = p.get("reliance_breakdown") or {}
            cheques.append({
                "cheque_id": f"rahkaran:{p.get('cheque_id')}",
                "system": "rahkaran",
                "channel": "b2b",
                "customer_key": f"rahkaran:{p.get('counterpart_ref')}",
                "customer_ref": p.get("counterpart_ref"),
                "customer_code": _code(p.get("counterpart_code")),
                "customer_name": name,
                "serial_number": _code(p.get("serial_number")),
                "amount_rial": amount,
                "reliance_percent": round(reliance, 2),
                "reliance_amount_rial": _round(amount * reliance / 100),
                "customer_base_reliance_percent": p.get("customer_base_reliance_percent"),
                "deductions": breakdown.get("deductions") or [],
                "reliance_reasons": p.get("reliance_reasons") or [],
                "resolved_history_count": p.get("resolved_history_count"),
                "due_date": due.isoformat(),
                "due_date_jalali": format_jalali_date(due),
                "days_to_due": (due - self.today).days,
                "holding": RAHKARAN_HOLDING.get(p.get("holding_label") or "", "cashbox"),
                "branch_name": None,
                "visitor_name": None,
                "hybrid_settlement": is_hybrid_counterpart(name),
            })
        returned = [{
            "system": "rahkaran", "customer_name": r.get("CustomerName"), "amount_rial": float(r["Amount"] or 0),
            "due_date": _as_date(r["DueDate"]),
        } for r in self._cached("rahkaran_returned", self.fetchers["rahkaran_returned"], refresh)]
        return cheques, returned

    # -- Karamad --------------------------------------------------------------

    def _karamad_status(self, status: int, due: date) -> str:
        """open / collected / returned_history / other, with the banked-then-cleared rule."""
        if status in KARAMAD_OPEN:
            if status == 3 and (due - self.today).days < -KARAMAD_BANKED_COLLECTED_AFTER_DAYS:
                return "collected"
            return "open"
        if status in KARAMAD_COLLECTED:
            return "collected"
        if status in KARAMAD_RETURNED:
            return "returned"
        return "other"  # 5 خرج شده, 11 انتقال بین شعب: outcome unknown, not history

    def _karamad(self, refresh: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        from app.services.finance_prediction_service import cheque_reliance_rules

        rows = [r for r in self._cached("karamad", self.fetchers["karamad"], refresh)
                if "تضمین" not in str(r.get("SLName") or "")]
        engine = CustomerChequeBehaviorEngine(allowed_term_days=ALLOWED_TERM_DAYS)
        stats: dict[Any, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        prepared = []
        for r in rows:
            due = _as_date(r["DueDate"])
            status = int(r["StatusRef"] or 0)
            kind = self._karamad_status(status, due)
            amount = float(r["Amount"] or 0)
            received = _as_date(r.get("ReceiptDate"))
            term = (due - received).days if received else None
            days = (due - self.today).days
            s = stats[r["CustomerRef"]]
            s["ChequeCount"] += 1
            s["TotalAmount"] += amount
            s["OverPolicyCount"] += 1 if term is not None and term > ALLOWED_TERM_DAYS else 0
            if kind == "collected":
                s["CollectedCount"] += 1
            elif kind == "returned":
                s["ReturnedCount"] += 1
            elif kind == "open":
                s["OpenCount"] += 1
                s["OpenAmount"] += amount
                if days < 0:
                    s["OverdueOpenCount"] += 1
                    s["OverdueOpenAmount"] += amount
                elif days <= 30:
                    s["UpcomingOpenAmount"] += amount
            prepared.append((r, due, status, kind, amount, term, days))

        customers: dict[Any, dict[str, Any]] = {}
        for ref, s in stats.items():
            row = dict(s)
            row["AverageChequeAmount"] = s["TotalAmount"] / s["ChequeCount"] if s["ChequeCount"] else 0.0
            prediction = engine.evaluate(row)
            prediction["historical_average_cheque_amount"] = row["AverageChequeAmount"]
            prediction["current_overdue_open_ratio_percent"] = prediction["customer_behavior"]["open_overdue_ratio_percent"]
            customers[ref] = prediction

        cheques, returned = [], []
        for r, due, status, kind, amount, term, days in prepared:
            if status in KARAMAD_RETURNED_OPEN:
                returned.append({"system": "karamad", "customer_name": r.get("CustomerName"),
                                 "amount_rial": amount, "due_date": due})
            if kind != "open":
                continue
            customer = customers.get(r["CustomerRef"])
            rules = cheque_reliance_rules(customer, amount, term, ALLOWED_TERM_DAYS)
            reliance = rules["cheque_reliance"]
            cheques.append({
                "cheque_id": f"karamad:{r['ChequeID']}",
                "system": "karamad",
                "channel": "hybrid",
                "customer_key": f"karamad:{r['CustomerRef']}",
                "customer_ref": r["CustomerRef"],
                "customer_code": _code(r.get("CustomerCode")),
                "customer_name": (r.get("CustomerName") or "").strip() or "مشتری نامشخص",
                "serial_number": _code(r.get("Serial")),
                "amount_rial": amount,
                "reliance_percent": round(reliance, 2),
                "reliance_amount_rial": _round(amount * reliance / 100),
                "customer_base_reliance_percent": round(rules["customer_reliance"], 2),
                "deductions": rules["deductions"],
                "reliance_reasons": rules["reliance_reasons"],
                "resolved_history_count": (customer or {}).get("customer_behavior", {}).get("resolved_cheque_count"),
                "due_date": due.isoformat(),
                "due_date_jalali": format_jalali_date(due),
                "days_to_due": days,
                "holding": KARAMAD_OPEN[status],
                "branch_name": (r.get("BranchName") or "").strip() or None,
                "visitor_name": (r.get("VisitorName") or "").strip() or None,
                "hybrid_settlement": False,
            })
        return cheques, returned

    # -- assembly -------------------------------------------------------------

    def _load(self, channel: SalesChannel, refresh: bool):
        cheques: list[dict[str, Any]] = []
        returned: list[dict[str, Any]] = []
        sources: list[str] = []
        warnings: list[dict[str, str]] = []
        loaders = {"rahkaran": self._rahkaran, "karamad": self._karamad}
        for system in CHANNEL_SYSTEMS[channel]:
            try:
                open_rows, returned_rows = loaders[system](refresh)
            except Exception as exc:
                warnings.append({
                    "code": f"{system}_unavailable",
                    "message": f"چک‌های دریافتی {'راهکاران' if system == 'rahkaran' else 'کارآمد'} دریافت نشد؛ اعداد ناقص است. ({exc.__class__.__name__})",
                })
                continue
            sources.append(system)
            cheques.extend(open_rows)
            returned.extend(returned_rows)
        return cheques, returned, sources, warnings

    @staticmethod
    def _sum(items: list[dict[str, Any]]) -> dict[str, Any]:
        definite = sum(c["amount_rial"] for c in items)
        reliance = sum(c["reliance_amount_rial"] for c in items)
        return {
            "definite_rial": _round(definite),
            "reliance_rial": _round(reliance),
            "collection_risk_rial": _round(definite - reliance),
            "reliance_percent": round(reliance / definite * 100, 1) if definite else None,
            "count": len(items),
        }

    @staticmethod
    def _filter(cheques, branch, visitor, holding, reliance_band, search):
        if branch:
            cheques = [c for c in cheques if c["branch_name"] and branch in c["branch_name"]]
        if visitor:
            cheques = [c for c in cheques if c["visitor_name"] and visitor in c["visitor_name"]]
        if holding:
            cheques = [c for c in cheques if c["holding"] == holding]
        if reliance_band in RELIANCE_BANDS:
            low, high = RELIANCE_BANDS[reliance_band]
            cheques = [c for c in cheques if (low is None or c["reliance_percent"] >= low)
                       and (high is None or c["reliance_percent"] < high)]
        if search:
            needle = search.strip().lower()
            cheques = [c for c in cheques if needle in c["customer_name"].lower()
                       or needle == (c["customer_code"] or "") or needle == (c["serial_number"] or "")]
        return cheques

    def schedule(self, horizon_days: int, channel: SalesChannel = "all", refresh: bool = False) -> dict[str, dict[str, float]]:
        """Daily «قطعی» and «اتکا» inflow inside the horizon (overdue cheques are not in the forecast)."""
        cheques, _, _, _ = self._load(channel, refresh)
        daily: dict[str, dict[str, float]] = defaultdict(lambda: {"definite_rial": 0.0, "reliance_rial": 0.0})
        for c in cheques:
            if c["hybrid_settlement"] or not 0 <= c["days_to_due"] < horizon_days:
                continue
            daily[c["due_date"]]["definite_rial"] += c["amount_rial"]
            daily[c["due_date"]]["reliance_rial"] += c["reliance_amount_rial"]
        return dict(daily)

    def report(self, horizon_days: int = 30, channel: SalesChannel = "all", branch: str | None = None,
               visitor: str | None = None, holding: str | None = None, reliance_band: str | None = None,
               search: str | None = None, refresh: bool = False) -> dict[str, Any]:
        horizon_days = max(1, min(int(horizon_days), 365))
        cheques, returned, sources, warnings = self._load(channel, refresh)
        cheques = self._filter(cheques, branch, visitor, holding, reliance_band, search)
        settlement = [c for c in cheques if c["hybrid_settlement"]]
        counted = [c for c in cheques if not c["hybrid_settlement"]]
        in_horizon = [c for c in counted if 0 <= c["days_to_due"] < horizon_days]
        overdue = [c for c in counted if c["days_to_due"] < 0]

        timeline = []
        by_day: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for c in in_horizon:
            by_day[c["days_to_due"]].append(c)
        for offset in range(horizon_days):
            day = self.today + timedelta(days=offset)
            timeline.append({"date": day.isoformat(), "date_jalali": format_jalali_date(day),
                             **self._sum(by_day.get(offset, []))})

        by_holding: dict[str, list[dict[str, Any]]] = defaultdict(list)
        by_channel: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for c in in_horizon:
            by_holding[c["holding"]].append(c)
            by_channel[c["channel"]].append(c)

        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for c in in_horizon:
            grouped[c["customer_key"]].append(c)
        customers = []
        for key, items in grouped.items():
            first = items[0]
            customers.append({
                "customer_key": key, "system": first["system"], "channel": first["channel"],
                "customer_code": first["customer_code"], "customer_name": first["customer_name"],
                **self._sum(items),
                "nearest_due_date_jalali": min(items, key=lambda c: c["days_to_due"])["due_date_jalali"],
                "resolved_history_count": first["resolved_history_count"],
            })
        customers.sort(key=lambda c: -c["collection_risk_rial"])

        buckets = []
        for low, high, label in OVERDUE_AGE_BUCKETS:
            items = [c for c in overdue if low <= -c["days_to_due"] and (high is None or -c["days_to_due"] <= high)]
            buckets.append({"label": label, **self._sum(items)})

        returned_card = {
            "amount_rial": _round(sum(r["amount_rial"] for r in returned)),
            "count": len(returned),
            "last_365_days_rial": _round(sum(r["amount_rial"] for r in returned
                                             if r["due_date"] and (self.today - r["due_date"]).days <= 365)),
            "by_system": [{"system": s, "channel": SYSTEM_CHANNEL[s], "label": CHANNEL_LABELS[SYSTEM_CHANNEL[s]],
                           "amount_rial": _round(sum(r["amount_rial"] for r in returned if r["system"] == s)),
                           "count": sum(1 for r in returned if r["system"] == s)}
                          for s in sorted({r["system"] for r in returned})],
            "in_totals": False,
            "rule": "چک برگشتی تسویه‌نشده (راهکاران: واخواست/حقوقی؛ کارآمد: برگشت نزد صندوق یا مشتری) فقط برای اطلاع است و در قطعی و اتکا نیست.",
        }

        today_items = [c for c in in_horizon if c["days_to_due"] == 0]
        next_7 = [c for c in in_horizon if c["days_to_due"] < 7]
        data = {
            "horizon": {"days": horizon_days, "from": self.today.isoformat(),
                        "to": (self.today + timedelta(days=horizon_days - 1)).isoformat(),
                        "from_jalali": format_jalali_date(self.today),
                        "to_jalali": format_jalali_date(self.today + timedelta(days=horizon_days - 1))},
            "kpis": {"horizon": self._sum(in_horizon), "today": self._sum(today_items), "next_7_days": self._sum(next_7)},
            "by_holding": [{"holding": h, "label": HOLDING_LABELS[h], **self._sum(items)}
                           for h, items in sorted(by_holding.items(), key=lambda kv: -sum(c["amount_rial"] for c in kv[1]))],
            "by_channel": [{"channel": ch, "label": CHANNEL_LABELS[ch], **self._sum(items)} for ch, items in by_channel.items()],
            "overdue": {**self._sum(overdue), "age_buckets": buckets, "in_totals": False,
                        "rule": "چک باز سررسیدگذشته جدا نمایش داده می‌شود و در قطعی و اتکای بازه نیست."},
            "returned_open": returned_card,
            "timeline": timeline,
            "customers": customers[:MAX_CUSTOMERS],
            "customer_count": len(customers),
            "hybrid_settlement": {
                **self._sum([c for c in settlement if 0 <= c["days_to_due"] < horizon_days]),
                "eliminated_in_group": channel == "all",
                "rule": "چک‌هایی که هیبرید بابت موجودی به شرکت داده (مشتری راهکاران «هیبرید …») تسویه داخلی است؛ در جمع گروه حساب نمی‌شود.",
            },
            "rule": "قطعی = ۱۰۰٪ مبلغ اسمی چک‌های باز بازه؛ اتکا = مبلغ × درصد اتکای هر چک (سابقه مشتری + قواعد چک). ریسک وصول = قطعی − اتکا.",
        }
        filters = {"horizon_days": horizon_days, "channel": channel, "branch": branch, "visitor": visitor,
                   "holding": holding, "reliance_band": reliance_band, "search": search}
        return {"status": "success", "as_of": self.today.isoformat(), "as_of_jalali": format_jalali_date(self.today),
                "filters": filters, "data": data, "sources": sources, "warnings": warnings}

    def customer_detail(self, system: str, customer_ref: str, refresh: bool = False) -> dict[str, Any]:
        channel: SalesChannel = "b2b" if system == "rahkaran" else "hybrid"
        cheques, _, sources, warnings = self._load(channel, refresh)
        key = f"{system}:{customer_ref}"
        items = sorted((c for c in cheques if c["customer_key"] == key), key=lambda c: c["days_to_due"])
        future = [c for c in items if c["days_to_due"] >= 0]
        return {
            "status": "success", "as_of": self.today.isoformat(), "as_of_jalali": format_jalali_date(self.today),
            "filters": {"system": system, "customer_ref": customer_ref},
            "data": {
                "customer_name": items[0]["customer_name"] if items else None,
                "open": self._sum(future),
                "overdue": self._sum([c for c in items if c["days_to_due"] < 0]),
                "cheques": [_public(c) for c in items],
            },
            "sources": sources, "warnings": warnings,
        }
