"""Authenticated API for the production forecast workspace."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from app.auth.guard import require_admin
from app.core.config import settings
from app.services import production_forecast as service

router = APIRouter(prefix="/forecast", tags=["production forecast"], default_response_class=JSONResponse)
DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩يك‌", "01234567890123456789یک ")


def norm(value):
    return str(value or "").translate(DIGITS).lower().strip()


def data():
    plan = service.snapshot("plan")
    if not plan:
        raise HTTPException(503, "هنوز برنامهٔ تولید منتشر نشده است.")
    return plan


@router.get("/overview")
def overview():
    return {
        **data()["overview"],
        "external": service.snapshot("external", {}),
        "jobs": {"plan": service.status("refresh"), "market": service.status("market")},
        "scheduler": {"enabled": settings.forecast_refresh_enabled, "plan_hour": "06:15",
                      "market_hour": "09:15", "market_day": "شنبه", "month_close_day": 3},
    }


@router.get("/categories")
def categories(period: Literal["monthly", "quarterly", "annual"] = "monthly",
               selected: str = Query("", max_length=12)):
    try:
        return service.category_production(data(), period, selected)
    except ValueError:
        raise HTTPException(422, "بازهٔ انتخاب‌شده در پیش‌بینی منتشرشده وجود ندارد.")


@router.get("/products")
def products(mode: Literal["production", "inventory", "demand", "safety"] = "production",
             horizon: int = Query(3), query: str = Query("", max_length=80),
             offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)):
    if horizon not in (1, 3, 6, 12):
        raise HTTPException(422, "افق باید ۱، ۳، ۶ یا ۱۲ ماه باشد.")
    needle = norm(query)
    rows = [row for row in data()["products"] if not needle or
            needle in norm(" ".join(str(row.get(k) or "") for k in ("code", "name", "brand", "category")))]
    if mode == "inventory":
        rows.sort(key=lambda row: row["factory_stock_1_4"] + row["branch_stock"], reverse=True)
    else:
        field = {"production": "production_need", "demand": "demand_3m", "safety": f"safety_{horizon}"}[mode]
        rows = [row for row in rows if row[field] > 0 or needle]
        rows.sort(key=lambda row: row[field], reverse=True)
    return {"total": len(rows), "rows": rows[offset:offset + limit]}


@router.get("/products/{code}")
def product(code: str):
    plan = data()
    record = next((row for row in plan["products"] if row["code"] == code), None)
    if record is None:
        raise HTTPException(404, "کالا پیدا نشد.")
    return {"product": record, "factory": plan["factory_details"].get(code, []),
            "branches": plan["branch_details"].get(code, [])}


@router.get("/rivals")
def rivals(channel: Literal["retail", "wholesale"] = "retail",
           category: str = Query("", max_length=40), query: str = Query("", max_length=80),
           offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    market = service.snapshot("market", {})
    entries = market.get("products", []) + market.get("live_products", [])
    words = norm(query).split()
    rows = [row for row in entries if row["channel"] == channel and (not category or row["category"] == category) and
            all(word in norm(" ".join(str(row.get(k) or "") for k in ("title", "brand", "company", "source"))) for word in words)]
    rows.sort(key=lambda row: (row["date"], row["source"], row["company"]), reverse=True)
    timeline = [x for x in market.get("retail_history", []) if channel == "retail" and x["category"] == category]
    return {"total": len(rows), "rows": rows[offset:offset + limit], "trend": timeline,
            "torob_observations": market.get("torob_observations"),
            "torob_last_date": market.get("torob_last_date"), "refreshed_at": market.get("live_updated_at"),
            "last_offer_date": rows[0]["date"] if rows else None}


@router.post("/refresh", status_code=202, dependencies=[Depends(require_admin)])
def refresh():
    if not service.launch("refresh", background=True):
        raise HTTPException(409, "به‌روزرسانی در حال اجراست.")
    return {"state": "running"}
