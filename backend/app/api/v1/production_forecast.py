"""Authenticated API for the production forecast workspace."""
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth.guard import require_admin
from app.core.config import settings
from app.services import production_forecast as service

router = APIRouter(prefix="/forecast", tags=["production forecast"], default_response_class=JSONResponse)
DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩يك‌", "01234567890123456789یک ")


class DistributorOverrideIn(BaseModel):
    key: str = Field(..., min_length=1, max_length=160)
    months: dict[str, float] = Field(default_factory=dict)
    note: str = Field("", max_length=240)


class PlannedEventIn(BaseModel):
    month: str = Field(..., pattern=r"^\d{4}/(0[1-9]|1[0-2])$")
    type: Literal["promotion", "price_hike", "event"] = "promotion"
    channel: Literal["all", "hybrid", "b2b"] = "all"
    scope: str = Field("همه", max_length=80)
    expected_lift_pct: float = Field(0.0, ge=-80.0, le=300.0)
    apply_to_forecast: bool = False
    note: str = Field("", max_length=240)


def norm(value):
    return str(value or "").translate(DIGITS).lower().strip()


def data():
    plan = service.snapshot("plan")
    if not plan:
        raise HTTPException(503, "هنوز برنامهٔ تولید منتشر نشده است.")
    return service.effective_plan(plan)


@router.get("/overview")
def overview():
    plan = data()
    base = plan["overview"]
    hz = service.overview_horizons(plan)
    return {
        **base,
        "totals": {**base["totals"], **hz["safety_totals"]},
        "horizons": hz["horizons"],
        "production_by_horizon": hz["production_by_horizon"],
        "external": service.external_with_live_usd(),
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


def _filtered_products(mode: str, horizon: int, query: str):
    if horizon not in service.HORIZONS:
        raise HTTPException(422, "افق باید ۱، ۲، ۳، ۴، ۶ یا ۱۲ ماه باشد.")
    plan = data()
    months = sorted(plan["overview"]["months"])
    needle = norm(query)
    matched = [row for row in plan["products"] if not needle or
               needle in norm(" ".join(str(row.get(k) or "") for k in ("code", "name", "brand", "category")))]
    rows = [{**row, **{k: v for k, v in service.product_horizons(row, months).items() if k != "monthly_breakdown"}}
            for row in matched]
    if mode == "inventory":
        rows.sort(key=lambda row: row["factory_stock_1_4"] + row["branch_stock"], reverse=True)
    else:
        field = {"production": f"production_need_{horizon}", "demand": f"demand_{horizon}", "safety": f"safety_{horizon}"}[mode]
        rows = [row for row in rows if row[field] > 0 or needle]
        rows.sort(key=lambda row: row[field], reverse=True)
    return months, rows


@router.get("/products")
def products(mode: Literal["production", "inventory", "demand", "safety"] = "production",
             horizon: int = Query(4), query: str = Query("", max_length=80),
             offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)):
    _, rows = _filtered_products(mode, horizon, query)
    return {"total": len(rows), "rows": rows[offset:offset + limit]}


@router.get("/products/export")
def export_products(mode: Literal["production", "inventory", "demand", "safety"] = "production",
                    horizon: int = Query(4), query: str = Query("", max_length=80)):
    months, rows = _filtered_products(mode, horizon, query)
    return {"months": months, "mode": mode, "horizon": horizon, "total": len(rows), "rows": rows}


@router.get("/products/{code}")
def product(code: str):
    plan = data()
    record = next((row for row in plan["products"] if row["code"] == code), None)
    if record is None:
        raise HTTPException(404, "کالا پیدا نشد.")
    months = sorted(plan["overview"]["months"])
    hz = service.product_horizons(record, months)
    enriched = {**record, **{k: v for k, v in hz.items() if k != "monthly_breakdown"}}
    return {"product": enriched, "monthly_breakdown": hz["monthly_breakdown"],
            "factory": plan["factory_details"].get(code, []),
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
    rows.sort(key=lambda row: (row.get("date") or "", row.get("source") or "", row.get("company") or ""), reverse=True)
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


@router.post("/refresh-market", status_code=202, dependencies=[Depends(require_admin)])
def refresh_market():
    if not service.launch("market", background=True):
        raise HTTPException(409, "به‌روزرسانی بازار در حال اجراست.")
    return {"state": "running"}


@router.get("/distributors")
def distributors(status: Literal["all", "due", "overridden"] = "all",
                 query: str = Query("", max_length=80),
                 offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)):
    doc = service.snapshot("distributors", {"closed_month": None, "months": [], "summary": {}, "rows": []})
    overrides = service.get_overrides().get("overrides", {})
    needle = norm(query)
    enriched = []
    for row in doc.get("rows", []):
        ov = overrides.get(row["key"])
        effective_fc = {
            m: float(ov["months"][m]) if (ov and m in ov.get("months", {})) else float(val)
            for m, val in row.get("forecast", {}).items()
        }
        base_total = float(row.get("total_forecast") or 0.0)
        eff_total = sum(effective_fc.values())
        item = {
            **row,
            "override": ov,
            "has_override": bool(ov),
            "effective_forecast": effective_fc,
            "effective_total": round(eff_total, 1),
            "delta_total": round(eff_total - base_total, 1),
        }
        if status == "due" and item["reorder_status"] not in ("overdue", "due_soon"):
            continue
        if status == "overridden" and not item["has_override"]:
            continue
        if needle:
            hay = norm(" ".join([item["distributor"], item["brand"], " ".join(item.get("accounts", []))]))
            if needle not in hay:
                continue
        enriched.append(item)
    summary = {
        **doc.get("summary", {}),
        "active_overrides": len(overrides),
        "override_delta_units": round(sum(r["delta_total"] for r in enriched if r["has_override"]), 1)
        if status == "all" and not needle else None,
    }
    if summary.get("override_delta_units") is None:
        all_rows = doc.get("rows", [])
        tot_delta = 0.0
        for r in all_rows:
            ov = overrides.get(r["key"])
            if ov:
                for m, bv in r.get("forecast", {}).items():
                    if m in ov.get("months", {}):
                        tot_delta += float(ov["months"][m]) - float(bv or 0.0)
        summary["override_delta_units"] = round(tot_delta, 1)
    return {
        "closed_month": doc.get("closed_month"),
        "months": doc.get("months", []),
        "summary": summary,
        "total": len(enriched),
        "rows": enriched[offset:offset + limit],
    }


@router.put("/distributors/overrides")
def save_distributor_override(payload: DistributorOverrideIn, admin: dict = Depends(require_admin)):
    doc = service.snapshot("distributors", {"rows": [], "months": []})
    row = next((r for r in doc.get("rows", []) if r["key"] == payload.key), None)
    if row is None:
        raise HTTPException(404, "ردیف توزیع‌کننده و برند پیدا نشد.")
    valid_months = set(doc.get("months", []))
    clean_months = {}
    for m, val in payload.months.items():
        if m not in valid_months:
            raise HTTPException(422, f"ماه {m} در افق فعال وجود ندارد.")
        if val < 0:
            raise HTTPException(422, "مقدار پیش‌بینی نمی‌تواند منفی باشد.")
        clean_months[m] = round(float(val), 1)
    entry = service.set_override(
        row["key"], row["distributor"], row["brand"], clean_months,
        note=payload.note, user=str(admin.get("username") or "admin"),
    )
    return {"override": entry}


@router.delete("/distributors/overrides/{key:path}", dependencies=[Depends(require_admin)])
def remove_distributor_override(key: str):
    if not service.delete_override(key):
        raise HTTPException(404, "تعدیلی برای این ردیف ثبت نشده است.")
    return {"deleted": key}


@router.get("/events")
def list_events():
    return service.get_events()


@router.post("/events", status_code=201)
def create_event(payload: PlannedEventIn, admin: dict = Depends(require_admin)):
    event = {
        "id": uuid4().hex[:12],
        "month": payload.month,
        "type": payload.type,
        "channel": payload.channel,
        "scope": payload.scope.strip() or "همه",
        "expected_lift_pct": round(float(payload.expected_lift_pct), 2),
        "apply_to_forecast": bool(payload.apply_to_forecast),
        "note": payload.note.strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": str(admin.get("username") or "admin"),
    }
    return {"event": service.add_event(event)}


@router.delete("/events/{event_id}", dependencies=[Depends(require_admin)])
def remove_event(event_id: str):
    if not service.delete_event(event_id):
        raise HTTPException(404, "رویداد پیدا نشد.")
    return {"deleted": event_id}


@router.get("/accuracy")
def accuracy():
    return service.snapshot("accuracy_history", {
        "closed_month": None,
        "archived_models": [],
        "live_evaluated_count": 0,
        "live_monthly": [],
        "pending_forecasts": [],
        "backtest_summary": {},
        "backtest_monthly": [],
    })


@router.get("/usd-live")
def usd_live(force: bool = False):
    ext = service.external_with_live_usd(force=force)
    usd = ext.get("usd")
    if not usd:
        raise HTTPException(503, "نرخ لحظه‌ای دلار در دسترس نیست.")
    return usd
