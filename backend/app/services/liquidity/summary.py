"""Liquidity summary: every section's schedule → daily net cash-flow forecast.

Management decision (1405/07/13): bank balances are not reliable yet (book balances only,
no bank statements), so the forecast starts from zero and shows the cumulative net flow:
received cheques + estimated collections − issued cheques − payroll − estimated outflows.
A negative cumulative position is the funding the period needs.  An opening balance can
still be typed in by hand when treasury knows it.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any

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
               opening_balance_rial: float | None = None, refresh: bool = False) -> dict[str, Any]:
        horizon_days = max(7, min(int(horizon_days), 180))
        today = self.today
        cash = CashMovementService(today=today)
        issued = IssuedChequeService(today=today)
        received = ReceivedChequeService(today=today)
        tasks = {
            "inflows": lambda: cash.inflows(base_days=base_days, channel=channel, refresh=refresh),
            "outflows": lambda: cash.outflows(base_days=base_days, channel=channel, refresh=refresh),
            "issued": lambda: issued.schedule(horizon_days, channel, refresh),
            "received": lambda: received.schedule(horizon_days, channel, refresh),
            "payroll": lambda: PayrollService(today=today).schedule(horizon_days, refresh, channel),
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
        for name in ("inflows", "outflows"):
            for w in (results.get(name) or {}).get("warnings", []):
                if w not in warnings:
                    warnings.append(w)

        opening = 0.0 if opening_balance_rial is None else float(opening_balance_rial)
        daily_in = ((results.get("inflows") or {}).get("data") or {}).get("forecast_basis", {}).get("daily_working_rial", 0.0)
        daily_out = ((results.get("outflows") or {}).get("data") or {}).get("forecast_basis", {}).get("daily_working_rial", 0.0)

        forecast = run_forecast(ForecastInputs(
            today=today, horizon_days=horizon_days, opening_balance_rial=opening,
            daily_inflow_rial=daily_in, daily_outflow_rial=daily_out,
            received=results.get("received") or {}, issued=results.get("issued") or {},
            payroll=results.get("payroll") or [],
        ))
        data = {
            "horizon": {"days": horizon_days, "from": today.isoformat(), "from_jalali": format_jalali_date(today)},
            "opening": {"used_rial": round(opening, 2), "source": "manual" if opening_balance_rial is not None else "none"},
            "basis": {
                "base_days": base_days,
                "daily_inflow_rial": daily_in,
                "daily_outflow_rial": daily_out,
                "method": "mean",
                "payroll": results.get("payroll") or [],
            },
            **forecast,
            "rule": "جریان نقد خالص از امروز: چک دریافتی (قطعی یا اتکا) + میانگین ورودی روز کاری − چک پرداختی − حقوق − میانگین خروجی روز کاری. موجودی بانک در محاسبه نیست؛ عدد منفی تجمعی یعنی تا آن روز خروجی از ورودی بیشتر بوده و باید از موجودی یا تأمین مالی پوشش داده شود. تسویه هیبرید با شرکت، سهامداران، وام و انتقال بین‌بانکی در پیش‌بینی نیستند.",
        }
        if channel != "all":
            warnings.append({"code": "channel_view",
                             "message": "در نمای یک کانال، تسویه هیبرید با شرکت در پیش‌بینی نیامده؛ پیش‌بینی قابل اتکا نمای «کل گروه» است."})
        sources = sorted({s for name in ("inflows", "outflows") for s in (results.get(name) or {}).get("sources", [])})
        return {"status": "success", "as_of": today.isoformat(), "as_of_jalali": format_jalali_date(today),
                "filters": {"horizon_days": horizon_days, "channel": channel, "base_days": base_days,
                            "opening_balance_rial": opening_balance_rial},
                "data": data, "sources": sources, "warnings": warnings}
