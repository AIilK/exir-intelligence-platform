"""Daily cash forecast (pure: no SQL, every input comes from the other sections).

closing(day) = opening
             + received cheques (قطعی or اتکا, per scenario)
             + estimated collections (mean working-day inflow × scenario factor)
             − issued cheques − payroll − estimated operating outflow (mean working day)

Fridays carry no estimated collection or outflow; dated items (cheques, payroll) land on
their own day whatever the weekday.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from app.utils.jalali import format_jalali_date

FRIDAY = 4


@dataclass(frozen=True)
class Scenario:
    key: str
    label: str
    cheque_field: str  # "definite_rial" or "reliance_rial"
    inflow_factor: float
    description: str


SCENARIOS = (
    Scenario("definite", "قطعی", "definite_rial", 1.0,
             "همه چک‌های دریافتی بازه ۱۰۰٪ وصول می‌شوند + میانگین ورودی نقد و حواله."),
    Scenario("reliance", "اتکا", "reliance_rial", 1.0,
             "چک دریافتی × درصد اتکای هر چک + میانگین ورودی نقد و حواله. سناریوی مبنا."),
    Scenario("pessimistic", "بدبینانه", "reliance_rial", 0.5,
             "چک دریافتی × درصد اتکا + فقط ۵۰٪ میانگین ورودی نقد و حواله."),
)
BASE_SCENARIO = "reliance"


@dataclass
class ForecastInputs:
    today: date
    horizon_days: int
    opening_balance_rial: float
    daily_inflow_rial: float
    daily_outflow_rial: float
    received: dict[str, dict[str, float]] = field(default_factory=dict)  # iso date → definite/reliance
    issued: dict[str, float] = field(default_factory=dict)
    payroll: list[dict[str, Any]] = field(default_factory=list)  # {"date", "amount_rial"}


def _round(value: float) -> float:
    return round(float(value), 2)


def run_scenario(inputs: ForecastInputs, scenario: Scenario) -> dict[str, Any]:
    payroll_by_day: dict[str, float] = {}
    for item in inputs.payroll:
        payroll_by_day[item["date"]] = payroll_by_day.get(item["date"], 0.0) + float(item["amount_rial"])

    balance = float(inputs.opening_balance_rial)
    days = []
    totals = {"received_cheques": 0.0, "estimated_inflow": 0.0,
              "issued_cheques": 0.0, "payroll": 0.0, "estimated_outflow": 0.0}
    first_shortage = None
    worst = {"balance_rial": balance, "date": inputs.today.isoformat(), "date_jalali": format_jalali_date(inputs.today)}
    for offset in range(inputs.horizon_days):
        day = inputs.today + timedelta(days=offset)
        key = day.isoformat()
        working = day.weekday() != FRIDAY
        flows = {
            "received_cheques": inputs.received.get(key, {}).get(scenario.cheque_field, 0.0),
            "estimated_inflow": inputs.daily_inflow_rial * scenario.inflow_factor if working else 0.0,
            "issued_cheques": inputs.issued.get(key, 0.0),
            "payroll": payroll_by_day.get(key, 0.0),
            "estimated_outflow": inputs.daily_outflow_rial if working else 0.0,
        }
        inflow = flows["received_cheques"] + flows["estimated_inflow"]
        outflow = flows["issued_cheques"] + flows["payroll"] + flows["estimated_outflow"]
        opening = balance
        balance = opening + inflow - outflow
        for name, value in flows.items():
            totals[name] += value
        row = {"date": key, "date_jalali": format_jalali_date(day), "weekday": day.weekday(),
               "opening_rial": _round(opening), **{f"{k}_rial": _round(v) for k, v in flows.items()},
               "inflow_rial": _round(inflow), "outflow_rial": _round(outflow),
               "net_rial": _round(inflow - outflow), "closing_rial": _round(balance)}
        days.append(row)
        if balance < 0 and first_shortage is None:
            first_shortage = {"date": key, "date_jalali": row["date_jalali"], "days_from_today": offset,
                              "closing_rial": row["closing_rial"]}
        if balance < worst["balance_rial"]:
            worst = {"balance_rial": _round(balance), "date": key, "date_jalali": row["date_jalali"]}

    total_in = totals["received_cheques"] + totals["estimated_inflow"]
    total_out = totals["issued_cheques"] + totals["payroll"] + totals["estimated_outflow"]
    return {
        "key": scenario.key,
        "label": scenario.label,
        "description": scenario.description,
        "opening_rial": _round(inputs.opening_balance_rial),
        "closing_rial": _round(balance),
        "totals": {f"{k}_rial": _round(v) for k, v in totals.items()},
        "inflow_rial": _round(total_in),
        "outflow_rial": _round(total_out),
        "first_shortage": first_shortage,
        "worst_balance": {**worst, "balance_rial": _round(worst["balance_rial"])},
        "financing_need_rial": _round(max(0.0, -worst["balance_rial"])),
        # (opening + inflows) / outflows: above 100 means the horizon is covered.
        "coverage_percent": round((inputs.opening_balance_rial + total_in) / total_out * 100, 1) if total_out else None,
        # Days until the balance first turns negative; None = covered for the whole horizon.
        "runway_days": first_shortage["days_from_today"] if first_shortage else None,
        "days": days,
    }


def run_forecast(inputs: ForecastInputs) -> dict[str, Any]:
    scenarios = [run_scenario(inputs, s) for s in SCENARIOS]
    return {"base_scenario": BASE_SCENARIO, "scenarios": scenarios}
