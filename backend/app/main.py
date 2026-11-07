import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.api.treasury import router as treasury_router
from app.api.v1.finance_dashboard import router as finance_dashboard_router
from app.api.v1.finance_operations import router as finance_operations_router
from app.api.v1.liquidity import router as liquidity_router
from app.chatbot.router import router as chatbot_router
from app.auth.router import router as auth_router
from app.auth.alarms import router as alarms_router
from app.auth.reminders import router as reminders_router
from app.auth.guard import auth_middleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.auth.store import init_tables
    init_tables()
    from app.automation.daily_finance_job import start_customer_scheduler, stop_customer_scheduler
    start_customer_scheduler()
    from app.services.karamad_sales_network_service import warm_up
    warm_up()
    import threading
    from app.services.cheque_registration import index as cheque_registration_index
    threading.Thread(target=cheque_registration_index, daemon=True).start()
    from app.chatbot.search import warm_up as chatbot_warm_up
    chatbot_warm_up()  # نمایه جستجوی چت‌بات و پرتفوی مشتریان از همان اول آماده باشد
    from app.services import manager_view_warmer
    manager_view_warmer.start()  # همه داده نمای مدیر از همان اول ساخته و تا وقتی کسی صفحه را می‌بیند گرم نگه داشته شود
    from app.core.config import settings
    if settings.hybrid_risk_weekly_enabled:
        def _hybrid_risk_catch_up():
            import time
            from app.services import hybrid_risk_service
            time.sleep(180)  # بعد از آماده‌سازی نمای مدیر، تا هم‌زمان روی دیتابیس فشار نیاورند
            hybrid_risk_service.ensure_recent()
            from app.services import ai_file_analysis_service
            time.sleep(300)  # تحلیل هوشمند از امتیاز ریسک تازه هم استفاده می‌کند
            ai_file_analysis_service.ensure_recent()
        threading.Thread(target=_hybrid_risk_catch_up, name="hybrid-risk-catch-up", daemon=True).start()
    yield
    stop_customer_scheduler()

logger = logging.getLogger(__name__)


class ChequeAwareJSONResponse(JSONResponse):
    """هر ردیف چک در پاسخ‌های JSON را با «ثبت در سیستم» (registered_at / registered_by) کامل می‌کند.

    قبلاً این کار در یک میدلور انجام می‌شد که بدنهٔ هر پاسخ را کامل در حافظه جمع، دوباره parse و دوباره
    سریالایز می‌کرد. حالا روی خروجی jsonable_encoder (که کپی تازه است، نه دادهٔ کش سرویس‌ها) و درست قبل از
    یک‌بار سریالایز شدن انجام می‌شود. اگر نمایهٔ ثبت چک هنوز ساخته نشده، پاسخ منتظر نمی‌ماند."""

    def render(self, content: Any) -> bytes:
        if isinstance(content, (dict, list)):
            try:
                from app.services.cheque_registration import annotate
                annotate(content, wait=False)
            except Exception:
                logger.exception("cheque registration annotate failed")
        return super().render(content)


app = FastAPI(
    title="Exir AI Platform",
    version="0.8.0",
    lifespan=lifespan,
    default_response_class=ChequeAwareJSONResponse,
)

# پاسخ‌های بزرگ (فهرست چک‌ها، گردش‌ها) فشرده روی شبکه می‌روند؛ حجم JSON را معمولاً ۵ تا ۲۰ برابر کم می‌کند.
app.add_middleware(GZipMiddleware, minimum_size=1024)

# ورود و سطح دسترسی ماژول‌ها (app/auth/guard.py)؛ قبل از CORS ثبت می‌شود تا CORS بیرونی‌تر باشد و پاسخ ۴۰۱/۴۰۳ هم هدر CORS بگیرد.
app.middleware("http")(auth_middleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_origin_regex=(
        r"^http://(?:localhost|127\.0\.0\.1|10(?:\.\d{1,3}){3}|"
        r"192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])"
        r"(?:\.\d{1,3}){2}):(?:3000|5173)$"
    ),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(finance_dashboard_router, prefix="/api/v1")
app.include_router(finance_operations_router, prefix="/api/v1")
app.include_router(treasury_router, prefix="/api/v1")
app.include_router(liquidity_router, prefix="/api/v1")
app.include_router(chatbot_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(alarms_router, prefix="/api/v1")
app.include_router(reminders_router, prefix="/api/v1")

@app.get("/")
def root():
    return {
        "status": "running",
        "message": "Exir AI Platform is running",
    }
