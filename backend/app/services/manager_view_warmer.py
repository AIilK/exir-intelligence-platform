"""داده نمای مدیر را از قبل آماده و گرم نگه می‌دارد تا هیچ کارتی منتظر SQL نماند.

- یک بار بلافاصله بعد از راه‌اندازی سرور، همه درخواست‌های نمای مدیر را (همان آدرس‌هایی که صفحه می‌خواند)
  یکی‌یکی صدا می‌زند تا کش‌ها پر شوند.
- تا وقتی کسی در ۲۰ دقیقه اخیر نمای مدیر را باز کرده، هر ۴ دقیقه (کمی قبل از انقضای کش ۵ دقیقه‌ای)
  دوباره همین کار را می‌کند؛ پس داده همیشه تازه است.
- وقتی کسی صفحه را نمی‌بیند (شب، تعطیلی) کاری نمی‌کند تا بار بی‌دلیل روی دیتابیس‌ها نباشد؛ اولین بازدید بعدی
  داده قبلی را فوراً می‌بیند و نسخه تازه در پس‌زمینه ساخته می‌شود (app/utils/swr_cache.py).
"""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

WARM_EVERY_SECONDS = 240
IDLE_AFTER_SECONDS = 20 * 60
_last_view = [0.0]
_started = threading.Event()


def touch() -> None:
    """صفحه نمای مدیر همین الان باز شده است (از endpoint مخصوص همان صفحه صدا زده می‌شود)."""
    _last_view[0] = time.time()


def _paths() -> list[str]:
    import jdatetime

    today = jdatetime.date.today()
    months = []
    for back in range(3):  # ماه جاری و دو ماه قبل (روند سه‌ماهه هیبریدها)
        idx = today.year * 12 + today.month - 1 - back
        months.append((idx // 12, idx % 12 + 1))
    (y, m) = months[0]
    paths = [
        "/liquidity/summary?horizon_days=30",
        "/liquidity/received-cheques?horizon_days=30",
        "/liquidity/received-cheques?horizon_days=365",
        "/liquidity/received-cheques/status/returned",
        "/liquidity/received-cheques/status/undetermined",
        "/liquidity/issued-cheques?horizon_days=365",
        "/liquidity/issued-cheques?horizon_days=30",
        "/liquidity/inflows?base_days=180&channel=all",
        "/liquidity/inflows?base_days=180&channel=hybrid",
        "/finance/sales-network",
        f"/finance/manager-combined?year={y}&month={m}",
        "/finance/payables",
        "/finance/process-health",
    ]
    paths += [f"/finance/distribution/monthly?year={yy}&month={mm}&view=summary" for yy, mm in months]
    paths += [f"/finance/pnl/{k}?source=live" for k in ("b2b", "export", "hybrid")]
    return paths


def warm_once() -> None:
    from app.utils.internal_api import internal_get

    started = time.monotonic()
    failed = []
    for path in _paths():
        try:
            internal_get(path)
        except Exception as exc:  # noqa: BLE001 — آماده‌سازی است؛ خطا در درخواست واقعی کاربر نشان داده می‌شود
            failed.append(f"{path}: {exc}")
    # جدول ویزیتورهای گزارش‌ساز اکسل (قبلاً در manager_combined_service.warm_up)
    try:
        from app.services.karamad_sales_network_service import KaramadSalesNetworkService
        KaramadSalesNetworkService().visitor_finance()
    except Exception as exc:  # noqa: BLE001
        failed.append(f"visitor_finance: {exc}")
    logger.info("manager view warmed in %.0fs%s", time.monotonic() - started,
                f" ({len(failed)} failed: {failed[:3]})" if failed else "")


def start() -> None:
    if _started.is_set():
        return
    _started.set()

    def loop() -> None:
        warm_once()
        while True:
            time.sleep(WARM_EVERY_SECONDS)
            if time.time() - _last_view[0] < IDLE_AFTER_SECONDS:
                warm_once()

    threading.Thread(target=loop, name="manager-view-warmer", daemon=True).start()
