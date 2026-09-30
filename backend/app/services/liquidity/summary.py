"""Liquidity summary: opening balance + every section's schedule → daily forecast."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any

from app.services.liquidity.bank_balances import BankBalanceService
from app.services.liquidity.cash_movements import CashMovementService, SalesChannel
from app.services.liquidity.forecast import ForecastInputs, run_forecast
from app.services.liquidity.issued_cheques import IssuedChequeService
from app.services.liquidity.payroll import PayrollService
from app.services.liquidity.received_cheques import ReceivedChequeService
from app.utils.jalali import format_jalali_date


class LiquiditySummaryService:
    def __init__(self, today: date | None = None):
        self.today = today or date.today()

    def report(self, horizon_days: int = 30, channel: SalesChannel = "all", base_days: int = 90,
               include_cash: bool = False, opening_balance_rial: float | None = None,
               refresh: bool = False) -> dict[str, Any]:
        horizon_days = max(7, min(int(horizon_days), 180))
        today = self.today
        cash = CashMovementService(today=today)
        issued = IssuedChequeService(today=today)
        received = ReceivedChequeService(today=today)
        tasks = {
            "balances": lambda: BankBalanceService(today=today).report(channel, refresh),
            "inflows": lambda: cash.inflows(base_days=base_days, channel=channel, refresh=refresh),
            "outflows": lambda: cash.outflows(base_days=base_days, channel=channel, refresh=refresh),
            "issued": lambda: issued.schedule(horizon_days, channel, refresh),
            "received": lambda: received.schedule(horizon_days, channel, refresh),
            "payroll": lambda: PayrollService(today=today).schedule(horizon_days, refresh) if channel != "hybrid" else [],
        }
        results: dict[str, Any] = {}
        warnings: list[dict[str, str]] = []
        # The sections read different databases; loading them together keeps the first call short.
        with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
            futures = {name: pool.submit(task) for name, task in tasks.items()}
            for name, future in futures.items():
                try:
                    results[name] = future.result()
                except Exception as exc:
                    results[name] = None
                    warnings.append({"code": f"{name}_failed",
                                     "message": f"بخش «{name}» محاسبه نشد و در پیش‌بینی صفر فرض شد. ({exc.__class__.__name__})"})
        for name in ("balances", "inflows", "outflows"):
            for w in (results.get(name) or {}).get("warnings", []):
                if w not in warnings:
                    warnings.append(w)

        balances = (results.get("balances") or {}).get("data") or {"bank_rial": 0.0, "cash_rial": 0.0}
        book_opening = balances["bank_rial"] + (balances["cash_rial"] if include_cash else 0.0)
        opening = book_opening if opening_balance_rial is None else float(opening_balance_rial)
        median_in = ((results.get("inflows") or {}).get("data") or {}).get("forecast_basis", {}).get("median_daily_working_rial", 0.0)
        median_out = ((results.get("outflows") or {}).get("data") or {}).get("forecast_basis", {}).get("median_daily_working_rial", 0.0)

        forecast = run_forecast(ForecastInputs(
            today=today, horizon_days=horizon_days, opening_balance_rial=opening,
            median_inflow_rial=median_in, median_outflow_rial=median_out,
            received=results.get("received") or {}, issued=results.get("issued") or {},
            payroll=results.get("payroll") or [],
        ))
        data = {
            "horizon": {"days": horizon_days, "from": today.isoformat(), "from_jalali": format_jalali_date(today)},
            "opening": {
                "used_rial": round(opening, 2),
                "source": "manual" if opening_balance_rial is not None else "book",
                "book_bank_rial": balances["bank_rial"],
                "book_cash_rial": balances["cash_rial"],
                "include_cash": include_cash,
                "by_system": balances.get("by_system", []),
                "excluded": balances.get("excluded", []),
            },
            "basis": {
                "base_days": base_days,
                "median_daily_inflow_rial": median_in,
                "median_daily_outflow_rial": median_out,
                "payroll": results.get("payroll") or [],
            },
            **forecast,
            "rule": "موجودی + چک دریافتی (قطعی یا اتکا) + میانه ورودی روز کاری − چک پرداختی − حقوق − میانه خروجی روز کاری. تسویه هیبرید با شرکت، چک‌های سهامداران (درون‌شرکتی)، وام و انتقال بین‌بانکی در پیش‌بینی نیستند.",
        }
        if channel != "all":
            warnings.append({"code": "channel_view",
                             "message": "در نمای یک کانال، تسویه هیبرید با شرکت در پیش‌بینی نیامده؛ پیش‌بینی قابل اتکا نمای «کل گروه» است."})
        return {"status": "success", "as_of": today.isoformat(), "as_of_jalali": format_jalali_date(today),
                "filters": {"horizon_days": horizon_days, "channel": channel, "base_days": base_days,
                            "include_cash": include_cash, "opening_balance_rial": opening_balance_rial},
                "data": data, "sources": (results.get("balances") or {}).get("sources", []), "warnings": warnings}
