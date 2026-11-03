import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from app.api.treasury import router as treasury_router
from app.api.v1.catalog import router as catalog_router
from app.api.v1.datasource import router as datasource_router
from app.api.v1.query import router as query_router
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
    yield
    stop_customer_scheduler()

app = FastAPI(
    title="Exir AI Platform",
    version="0.8.0",
    lifespan=lifespan,
)

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

@app.middleware("http")
async def cheque_registration_middleware(request: Request, call_next):
    """هر ردیف چک در پاسخ‌های JSON را با «ثبت در سیستم» (registered_at / registered_by) کامل می‌کند."""
    response = await call_next(request)
    if request.method != "GET" or not response.headers.get("content-type", "").startswith("application/json"):
        return response
    body = b"".join([chunk async for chunk in response.body_iterator])
    headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
    if b'"due_date' in body and len(body) < 80_000_000:
        try:
            from app.services.cheque_registration import annotate
            payload = json.loads(body)
            if await run_in_threadpool(annotate, payload):
                body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        except Exception:
            pass
    return Response(content=body, status_code=response.status_code, headers=headers, media_type=response.media_type)


app.include_router(datasource_router, prefix="/api/v1")
app.include_router(catalog_router, prefix="/api/v1")
app.include_router(query_router, prefix="/api/v1")
app.include_router(finance_dashboard_router, prefix="/api/v1")
app.include_router(finance_operations_router, prefix="/api/v1")
app.include_router(treasury_router, prefix="/api/v1")
app.include_router(liquidity_router, prefix="/api/v1")
app.include_router(chatbot_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(alarms_router, prefix="/api/v1")
app.include_router(reminders_router, prefix="/api/v1")

from app.api.v1.finance_agent import router as finance_agent_router


app.include_router(
    finance_agent_router,
    prefix="/api/v1"
)
@app.get("/")
def root():
    return {
        "status": "running",
        "message": "Exir AI Platform is running",
    }
