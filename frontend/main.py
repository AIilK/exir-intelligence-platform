from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.treasury import router as treasury_router
from app.api.v1.catalog import router as catalog_router
from app.api.v1.datasource import router as datasource_router
from app.api.v1.query import router as query_router
from app.api.v1.finance_dashboard import router as finance_dashboard_router
from app.api.v1.finance_operations import router as finance_operations_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.automation.daily_finance_job import start_customer_scheduler, stop_customer_scheduler
    start_customer_scheduler()
    yield
    stop_customer_scheduler()

app = FastAPI(
    title="Exir AI Platform",
    version="0.3.0",
    lifespan=lifespan,
)

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
    allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(datasource_router, prefix="/api/v1")
app.include_router(catalog_router, prefix="/api/v1")
app.include_router(query_router, prefix="/api/v1")
app.include_router(finance_dashboard_router, prefix="/api/v1")
app.include_router(finance_operations_router, prefix="/api/v1")
app.include_router(treasury_router, prefix="/api/v1")

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
