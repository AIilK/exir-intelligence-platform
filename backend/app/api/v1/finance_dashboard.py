from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from pathlib import Path
from tempfile import NamedTemporaryFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from app.services.finance_dashboard_service import FinanceDashboardService


router = APIRouter(prefix="/finance", tags=["finance-intelligence"])

class AlertUpdate(BaseModel):
    status: str
    assignee: str | None = None


def _refresh_finance_agents_after_karamad_import(result: dict) -> dict:
    """Refresh agent reports after a successful KarAmand snapshot update.

    Import success is never rolled back if SQL/LLM refresh is temporarily unavailable.
    The response tells the UI whether the new report was generated or still needs a retry.
    """
    try:
        from app.services.finance_operations_service import FinanceAgentOrchestrator
        refreshed = FinanceAgentOrchestrator().run_all(trigger="karamad_snapshot_update")
        result["agent_refresh"] = {
            "status": "success",
            "report_id": refreshed.get("report_id"),
            "data_version": refreshed.get("data_version"),
            "generated_at": refreshed.get("generated_at"),
        }
    except Exception as exc:
        result["agent_refresh"] = {
            "status": "pending",
            "message": "فایل ثبت شد، اما گزارش Agentها در این لحظه بازسازی نشد؛ اجرای دستی Agentها دوباره تلاش می‌کند.",
            "error": f"{type(exc).__name__}: {str(exc)[:240]}",
        }
    return result


@router.post("/cashflow-excel/upload", summary="بارگذاری روزانه Cash Flow و تحلیل خودکار ماه شمسی")
async def upload_daily_cashflow_excel(file: UploadFile = File(...)):
    from app.services.monthly_cashflow_excel_service import MonthlyCashflowExcelService
    filename = Path(file.filename or "").name
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="فقط فایل Excel با پسوند xlsx مجاز است.")
    temporary: Path | None = None
    try:
        content = await file.read()
        if len(content) > 25 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="حجم فایل نباید بیشتر از ۲۵ مگابایت باشد.")
        with NamedTemporaryFile(delete=False, suffix=".xlsx") as handle:
            handle.write(content)
            temporary = Path(handle.name)
        return MonthlyCashflowExcelService().save_upload(temporary, filename)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"پردازش فایل Cash Flow با خطا مواجه شد: {exc}") from exc
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


@router.get("/cashflow-excel/months", summary="ماه‌های دارای فایل Cash Flow")
def cashflow_excel_months():
    from app.services.monthly_cashflow_excel_service import MonthlyCashflowExcelService
    return {"status": "success", "months": MonthlyCashflowExcelService().months()}


@router.get("/cashflow-excel/folder/status", summary="وضعیت پوشه خودکار Cash Flow")
def cashflow_excel_folder_status():
    from app.services.cashflow_folder_import_service import CashflowFolderImportService
    return CashflowFolderImportService().status()


@router.post("/cashflow-excel/folder/scan", summary="بررسی فوری پوشه خودکار Cash Flow")
def cashflow_excel_folder_scan():
    from app.services.cashflow_folder_import_service import CashflowFolderImportService
    try:
        return CashflowFolderImportService().scan()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"بررسی پوشه Cash Flow با خطا مواجه شد: {exc}") from exc


@router.get("/cashflow-excel/analysis", summary="تحلیل Cash Flow از ابتدای ماه شمسی انتخاب‌شده")
def cashflow_excel_analysis(
    jalali_year: int = Query(..., ge=1300, le=1500),
    jalali_month: int = Query(..., ge=1, le=12),
):
    from app.services.monthly_cashflow_excel_service import MonthlyCashflowExcelService
    return MonthlyCashflowExcelService().analyze(jalali_year, jalali_month)

@router.get("/cashflow-excel/files/{jalali_year}/{jalali_month}/{stored_file}/preview", summary="نمایش شیت‌های فایل Cash Flow")
def cashflow_excel_preview(jalali_year: int, jalali_month: int, stored_file: str):
    from app.services.monthly_cashflow_excel_service import MonthlyCashflowExcelService
    try:
        return MonthlyCashflowExcelService().workbook_preview(jalali_year, jalali_month, stored_file)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

@router.get("/cashflow-excel/files/{jalali_year}/{jalali_month}/{stored_file}/download", summary="دانلود فایل اصلی Cash Flow")
def cashflow_excel_download(jalali_year: int, jalali_month: int, stored_file: str):
    from app.services.monthly_cashflow_excel_service import MonthlyCashflowExcelService
    try:
        path = MonthlyCashflowExcelService().stored_workbook(jalali_year, jalali_month, stored_file)
        return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=stored_file.split("__", 1)[-1])
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/karamad-payment-transfers/upload", summary="ورود حواله‌های پرداختی کارآمد از Excel")
async def upload_karamad_payment_transfers(file: UploadFile = File(...)):
    from app.services.karamad_payment_transfer_service import KaramadPaymentTransferService

    filename = Path(file.filename or "").name
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="فقط فایل Excel با پسوند xlsx مجاز است.")
    temporary: Path | None = None
    try:
        content = await file.read()
        if len(content) > 25 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="حجم فایل نباید بیشتر از ۲۵ مگابایت باشد.")
        with NamedTemporaryFile(delete=False, suffix=".xlsx") as handle:
            handle.write(content)
            temporary = Path(handle.name)
        return KaramadPaymentTransferService().import_workbook(temporary, filename)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"پردازش حواله‌های کارآمد با خطا مواجه شد: {exc}") from exc
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


@router.get("/karamad-payment-transfers", summary="فهرست حواله‌های پرداختی واردشده از کارآمد")
def karamad_payment_transfers(
    month: str | None = Query(default=None, description="ماه شمسی مانند 1405/06"),
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
):
    from app.services.karamad_payment_transfer_service import KaramadPaymentTransferService

    try:
        return KaramadPaymentTransferService().report(
            month=month, search=search, limit=limit, offset=offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/karamad-manual/folder/status", summary="وضعیت پوشه ورود خودکار چهار فایل کارآمد")
def karamad_manual_folder_status():
    from app.services.karamad_manual_import_service import KaramadManualImportService
    return KaramadManualImportService().status()


@router.post("/karamad-manual/folder/scan", summary="بررسی فوری پوشه چهار فایل کارآمد")
def karamad_manual_folder_scan():
    from app.services.karamad_manual_import_service import KaramadManualImportService
    try:
        result = KaramadManualImportService().scan()
        if result.get("imported_count"):
            return _refresh_finance_agents_after_karamad_import(result)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"بررسی پوشه کارآمد با خطا مواجه شد: {exc}") from exc


@router.post("/karamad-manual/upload", summary="ورود دستی یکی از چهار خروجی کارآمد")
async def upload_karamad_manual(
    file: UploadFile = File(...),
    source_kind: str | None = Query(default=None, pattern="^(received_cheques|issued_cheques|received_transfers|paid_transfers)$"),
):
    from app.services.karamad_manual_import_service import KaramadManualImportService
    filename = Path(file.filename or "").name
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="فقط فایل Excel با پسوند xlsx مجاز است.")
    temporary: Path | None = None
    try:
        content = await file.read()
        if len(content) > 25 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="حجم فایل نباید بیشتر از ۲۵ مگابایت باشد.")
        with NamedTemporaryFile(delete=False, suffix=".xlsx") as handle:
            handle.write(content)
            temporary = Path(handle.name)
        result = KaramadManualImportService().import_workbook(temporary, filename, source_kind)
        return _refresh_finance_agents_after_karamad_import(result)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"پردازش فایل کارآمد با خطا مواجه شد: {exc}") from exc
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


@router.post("/karamad-manual/received-cheques/replace", summary="جایگزینی کامل سبد چک‌های دریافتی کارآمد")
async def replace_karamad_received_cheques(file: UploadFile = File(...)):
    from app.services.karamad_manual_import_service import KaramadManualImportService
    filename = Path(file.filename or "").name
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="برای به‌روزرسانی سبد چک دریافتی فقط فایل xlsx مجاز است.")
    temporary: Path | None = None
    try:
        content = await file.read()
        if len(content) > 25 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="حجم فایل نباید بیشتر از ۲۵ مگابایت باشد.")
        with NamedTemporaryFile(delete=False, suffix=".xlsx") as handle:
            handle.write(content)
            temporary = Path(handle.name)
        result = KaramadManualImportService().import_workbook(temporary, filename, "received_cheques")
        if not result.get("import", {}).get("snapshot_replace") and not result.get("duplicate_file"):
            raise HTTPException(status_code=422, detail="این فایل ساختار سبد کامل چک‌های دریافتی کارآمد را ندارد.")
        return _refresh_finance_agents_after_karamad_import(result)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"به‌روزرسانی سبد چک دریافتی کارآمد با خطا مواجه شد: {exc}") from exc
    finally:
        if temporary and temporary.exists():
            temporary.unlink()




@router.post("/karamad-manual/issued-cheques/replace", summary="جایگزینی چک‌های پرداختی ثبت‌شده کارآمد")
async def replace_karamad_issued_cheques(file: UploadFile = File(...)):
    from app.services.karamad_manual_import_service import KaramadManualImportService
    filename = Path(file.filename or "").name
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="برای به‌روزرسانی چک‌های پرداختی ثبت‌شده فقط فایل xlsx مجاز است.")
    temporary: Path | None = None
    try:
        content = await file.read()
        if len(content) > 25 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="حجم فایل نباید بیشتر از ۲۵ مگابایت باشد.")
        with NamedTemporaryFile(delete=False, suffix=".xlsx") as handle:
            handle.write(content)
            temporary = Path(handle.name)
        result = KaramadManualImportService().import_workbook(temporary, filename, "issued_cheques")
        imported = result.get("import", {})
        if not result.get("duplicate_file") and (not imported.get("snapshot_replace") or imported.get("snapshot_kind") != "issued_cheques"):
            raise HTTPException(status_code=422, detail="این فایل ساختار چک‌های پرداختی ثبت‌شده کارآمد را ندارد.")
        return _refresh_finance_agents_after_karamad_import(result)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"به‌روزرسانی چک‌های پرداختی کارآمد با خطا مواجه شد: {exc}") from exc
    finally:
        if temporary and temporary.exists():
            temporary.unlink()

@router.get("/karamad-manual/movements", summary="گردش یکتاشده چهار فایل کارآمد")
def karamad_manual_movements(
    month: str | None = Query(default=None, description="ماه شمسی مانند 1405/06"),
    direction: str | None = Query(default=None, pattern="^(inflow|outflow)$"),
    classification: str | None = Query(default=None, pattern="^(operational|company_bank_transfer|petty_cash)$"),
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    branch: str | None = Query(default=None, max_length=200),
):
    from app.services.karamad_manual_import_service import KaramadManualImportService
    try:
        return KaramadManualImportService().report(month, direction, classification, search, limit, offset, branch)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/karamad-manual/customer-summary", summary="خلاصه رفتار مشتری از داده‌های کارآمد با فیلتر شعبه")
def karamad_customer_summary(branch: str | None = Query(default=None, max_length=200)):
    # V159: live SQL first (transfers + received cheques; issued cheques still
    # merged in from the manual snapshot inside the live service itself),
    # falling back to the fully-manual snapshot only if the live source errors.
    try:
        from app.services.karamad_live_customer_activity_service import KaramadLiveCustomerActivityService
        return KaramadLiveCustomerActivityService().customer_summary(branch=branch)
    except Exception:
        from app.services.karamad_manual_import_service import KaramadManualImportService
        return KaramadManualImportService().customer_summary(branch=branch)


@router.get("/karamad-manual/customer-detail", summary="ریز چک و حواله یک مشتری از کارآمد")
def karamad_customer_detail(
    customer_name: str = Query(..., min_length=1, max_length=300),
    branch: str | None = Query(default=None, max_length=200),
):
    try:
        from app.services.karamad_live_customer_activity_service import KaramadLiveCustomerActivityService
        return KaramadLiveCustomerActivityService().customer_detail(customer_name=customer_name, branch=branch)
    except Exception:
        from app.services.karamad_manual_import_service import KaramadManualImportService
        return KaramadManualImportService().customer_detail(customer_name=customer_name, branch=branch)


@router.post("/customer-automation/run", summary="اجرای فوری اتوماسیون رفتار مشتری")
def run_customer_automation():
    from app.services.customer_automation_service import CustomerAutomationService
    try: return CustomerAutomationService().run(trigger="manual")
    except Exception as exc: raise HTTPException(status_code=500, detail=f"اجرای اتوماسیون با خطا مواجه شد: {exc}") from exc

@router.get("/customer-automation/status", summary="وضعیت زمان‌بندی و آخرین اجراها")
def customer_automation_status():
    from app.automation.daily_finance_job import scheduler_status
    from app.services.customer_automation_service import CustomerAutomationStore
    return {"scheduler":scheduler_status(),"recent_runs":CustomerAutomationStore().recent_runs()}

@router.get("/customer-automation/latest", summary="آخرین خروجی کامل اتوماسیون و Agent")
def customer_automation_latest():
    from app.services.customer_automation_service import CustomerAutomationStore
    payload = CustomerAutomationStore().latest_payload()
    if payload is None:
        return {"status": "empty", "message": "هنوز اجرای موفق ذخیره‌شده‌ای وجود ندارد."}
    return payload

@router.get("/customer-agent/status", summary="وضعیت Customer Behavior Agent")
def customer_agent_status():
    from app.core.config import settings
    from app.services.customer_automation_service import CustomerAutomationStore
    latest = CustomerAutomationStore().recent_runs(limit=1)
    return {
        "status": "ready" if settings.customer_behavior_agent_enabled else "disabled",
        "agent_name": "Customer Behavior Agent",
        "llm_configured": bool(settings.openai_api_key),
        "model": settings.customer_behavior_agent_model or settings.openai_model,
        "fallback_available": True,
        "last_run": latest[0] if latest else None,
    }


@router.get(
    "/customer-cheque-behavior",
    summary="امتیاز خوش‌قولی و سیاست پذیرش چک تمام مشتریان",
)
def customer_cheque_behavior(
    history_days: int = Query(default=365, ge=30, le=730),
    forecast_days: int = Query(default=30, ge=7, le=180),
    allowed_term_days: int = Query(default=90, ge=1, le=365),
    limit: int | None = Query(default=200, ge=1, le=5000),
):
    from app.services.finance_prediction_service import FinancePredictionService

    try:
        return FinancePredictionService(
            history_days=history_days,
            forecast_days=forecast_days,
            allowed_term_days=allowed_term_days,
        ).customer_predictions(limit=limit)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"تحلیل رفتار چکی مشتریان با خطا مواجه شد: {exc}",
        ) from exc

@router.get("/customer-alerts", summary="هشدارهای قابل پیگیری مشتری")
def customer_alerts(alert_status: str=Query(default="open",alias="status"),limit:int=Query(default=100,ge=1,le=500)):
    from app.services.customer_automation_service import CustomerAutomationStore
    return {"status":"success","alerts":CustomerAutomationStore().list_alerts(alert_status,limit)}

@router.patch("/customer-alerts/{alert_id}", summary="تایید، ارجاع یا حل هشدار")
def update_customer_alert(alert_id:str,body:AlertUpdate):
    if body.status not in {"open","acknowledged","in_progress","resolved"}: raise HTTPException(status_code=422,detail="وضعیت هشدار نامعتبر است.")
    from app.services.customer_automation_service import CustomerAutomationStore
    if not CustomerAutomationStore().update_alert(alert_id,body.status,body.assignee): raise HTTPException(status_code=404,detail="هشدار پیدا نشد.")
    return {"status":"success","alert_id":alert_id,"new_status":body.status}

@router.get("/representative-intelligence", summary="تحلیل رفتار مشتریان به تفکیک نماینده")
def representative_intelligence():
    from app.services.customer_intelligence_service import CustomerIntelligenceService
    from app.services.representative_intelligence_service import RepresentativeIntelligenceService
    try: return RepresentativeIntelligenceService().aggregate(CustomerIntelligenceService().dashboard(limit=1000)["customers"])
    except Exception as exc: raise HTTPException(status_code=500,detail=f"تحلیل نمایندگان با خطا مواجه شد: {exc}") from exc


@router.get("/representative-mapping/template.csv", summary="دانلود قالب ارتباط مشتری و نماینده")
def representative_mapping_template():
    from app.services.customer_intelligence_service import CustomerIntelligenceService
    from app.services.representative_intelligence_service import RepresentativeIntelligenceService
    try:
        customers = CustomerIntelligenceService().dashboard(limit=1000)["customers"]
        content = RepresentativeIntelligenceService.build_template(customers)
        return Response(
            content=content.encode("utf-8"),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="customer_representative_mapping.csv"'},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"ساخت قالب نمایندگان با خطا مواجه شد: {exc}") from exc


@router.post("/representative-mapping/upload", summary="بارگذاری ارتباط مشتری و نماینده")
async def representative_mapping_upload(file: UploadFile = File(...)):
    from app.services.customer_intelligence_service import CustomerIntelligenceService
    from app.services.representative_intelligence_service import RepresentativeIntelligenceService
    if not str(file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=422, detail="فقط فایل CSV مجاز است.")
    try:
        customers = CustomerIntelligenceService().dashboard(limit=1000)["customers"]
        valid_refs = {str(item["counterpart_ref"]) for item in customers}
        result = RepresentativeIntelligenceService().save_mapping(await file.read(), valid_refs)
        result["analysis"] = RepresentativeIntelligenceService().aggregate(customers)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"بارگذاری Mapping نمایندگان با خطا مواجه شد: {exc}") from exc


@router.get("/customer-intelligence", summary="داشبورد هوشمند رفتار مشتری")
def customer_intelligence(
    history_days: int = Query(default=365, ge=30, le=730),
    forecast_days: int = Query(default=30, ge=1, le=180),
    allowed_term_days: int = Query(default=90, ge=1, le=365),
    limit: int = Query(default=200, ge=1, le=1000),
):
    from app.services.customer_intelligence_service import CustomerIntelligenceService
    try:
        return CustomerIntelligenceService(
            history_days=history_days,
            forecast_days=forecast_days,
            allowed_term_days=allowed_term_days,
        ).dashboard(limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"تحلیل رفتار مشتری با خطا مواجه شد: {exc}") from exc


@router.get("/customer-collection-portfolio", summary="پرتفوی جامع مطالبات و پوشش وصول مشتریان")
def customer_collection_portfolio(
    limit: int = Query(default=300, ge=1, le=1000),
    source: str = Query(default="rahkaran", pattern="^(rahkaran|karamad)$"),
    branch: str | None = Query(default=None, max_length=200),
):
    if source == "karamad":
        from app.services.karamad_live_customer_activity_service import KaramadLiveCustomerActivityService
        try:
            return KaramadLiveCustomerActivityService().collection_portfolio(branch=branch, limit=limit)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"بارگذاری ماژول جامع مطالبات مشتریان کارآمد با خطا مواجه شد: {exc}") from exc
    from app.services.customer_intelligence_service import CustomerIntelligenceService
    try:
        return CustomerIntelligenceService().collection_portfolio(limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"بارگذاری ماژول جامع مطالبات مشتریان با خطا مواجه شد: {exc}") from exc


@router.get("/customer-file/rahkaran/{counterpart_ref}", summary="پرونده مشتری راهکاران: فاکتورهای خرید و ۵ فاکتور آخر")
def customer_file_rahkaran(counterpart_ref: int):
    from app.services.customer_file_service import CustomerFileService
    try:
        return CustomerFileService().rahkaran(counterpart_ref)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"دریافت فاکتورهای مشتری از راهکاران با خطا مواجه شد: {exc}") from exc


@router.get("/customer-file/karamad", summary="پرونده مشتری کارآمد: فاکتورها، ۵ فاکتور آخر و ویزیتور/سرپرست/هیبرید")
def customer_file_karamad(dl_refs: str = Query(..., min_length=1, max_length=2000, pattern=r"^\d+(,\d+)*$")):
    from app.services.customer_file_service import CustomerFileService
    try:
        return CustomerFileService().karamad([int(x) for x in dl_refs.split(",")])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"دریافت فاکتورهای مشتری از کارآمد با خطا مواجه شد: {exc}") from exc


@router.get("/sales-network", summary="شبکه فروش کارآمد: هیبرید من‌ها به تفکیک شعبه")
def sales_network_overview():
    from app.services.karamad_sales_network_service import KaramadSalesNetworkService
    try:
        return KaramadSalesNetworkService().overview()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"دریافت شبکه فروش کارآمد با خطا مواجه شد: {exc}") from exc


@router.get("/sales-network/branches/{branch_id}", summary="پرونده هیبرید (شعبه): فروش، ویزیتورها، مطالبات و چک‌ها")
def sales_network_branch(branch_id: int):
    from app.services.karamad_sales_network_service import KaramadSalesNetworkService
    try:
        result = KaramadSalesNetworkService().branch_file(branch_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"دریافت پرونده شعبه با خطا مواجه شد: {exc}") from exc
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="شعبه پیدا نشد.")
    return result


@router.get("/sales-network/visitors/{visitor_id}", summary="پرونده ویزیتور: فروش، مطالبات و چک‌ها")
def sales_network_visitor(visitor_id: int):
    from app.services.karamad_sales_network_service import KaramadSalesNetworkService
    try:
        result = KaramadSalesNetworkService().visitor_file(visitor_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"دریافت پرونده ویزیتور با خطا مواجه شد: {exc}") from exc
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="ویزیتور پیدا نشد.")
    return result


@router.get("/customer-intelligence/{counterpart_ref}", summary="تحلیل انسانی رفتار یک مشتری")
def customer_intelligence_detail(
    counterpart_ref: int,
    history_days: int = Query(default=365, ge=30, le=730),
    forecast_days: int = Query(default=30, ge=1, le=180),
    allowed_term_days: int = Query(default=90, ge=1, le=365),
):
    from app.services.customer_intelligence_service import CustomerIntelligenceService
    try:
        return CustomerIntelligenceService(
            history_days=history_days,
            forecast_days=forecast_days,
            allowed_term_days=allowed_term_days,
        ).customer(counterpart_ref)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"تحلیل مشتری با خطا مواجه شد: {exc}") from exc


@router.get(
    "/dashboard",
    summary="داشبورد هوشمند مالی از SQL Server شرکت",
)
def finance_dashboard(
    allowed_term_days: int = Query(default=90, ge=1, le=365),
    history_days: int = Query(default=365, ge=30, le=730),
    forecast_days: int = Query(default=30, ge=1, le=180),
    opening_cash: float | None = Query(
        default=None,
        ge=0,
        description="اختیاری؛ اگر مانده نقد قطعی موجود است برای سناریوی نقدینگی استفاده می‌شود.",
    ),
):
    try:
        return FinanceDashboardService(
            allowed_term_days=allowed_term_days,
            history_days=history_days,
            forecast_days=forecast_days,
            opening_cash=opening_cash,
        ).build_dashboard()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"ساخت داشبورد مالی از SQL Server با خطا مواجه شد: {exc}",
        ) from exc


@router.get(
    "/dashboard/health",
    summary="بررسی اتصال منبع SQL داشبورد مالی",
)
def finance_dashboard_health():
    try:
        return FinanceDashboardService().health()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"SQL Server dashboard source is unavailable: {exc}",
        ) from exc


@router.get(
    "/predictions/customers",
    summary="پیش‌بینی وصول، دیرکرد و ریسک برگشت به تفکیک مشتری",
)
def customer_predictions(
    history_days: int = Query(default=365, ge=30, le=730),
    forecast_days: int = Query(default=30, ge=1, le=180),
    allowed_term_days: int = Query(default=90, ge=1, le=365),
    limit: int = Query(default=200, ge=1, le=1000),
):
    from app.services.finance_prediction_service import FinancePredictionService

    try:
        return FinancePredictionService(
            history_days=history_days,
            forecast_days=forecast_days,
            allowed_term_days=allowed_term_days,
        ).customer_predictions(limit=limit)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"پیش‌بینی مشتریان با خطا مواجه شد: {exc}",
        ) from exc


@router.get(
    "/predictions/customers/{counterpart_ref}",
    summary="پیش‌بینی وصول و ریسک یک مشتری",
)
def customer_prediction(
    counterpart_ref: int,
    history_days: int = Query(default=365, ge=30, le=730),
    forecast_days: int = Query(default=30, ge=1, le=180),
    allowed_term_days: int = Query(default=90, ge=1, le=365),
):
    from app.services.finance_prediction_service import FinancePredictionService

    try:
        return FinancePredictionService(
            history_days=history_days,
            forecast_days=forecast_days,
            allowed_term_days=allowed_term_days,
        ).customer_prediction(counterpart_ref)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"پیش‌بینی مشتری با خطا مواجه شد: {exc}",
        ) from exc


@router.get(
    "/predictions/cheque-return",
    summary="برآورد توضیح‌پذیر احتمال برگشت چک‌های دریافتی آینده",
)
def cheque_return_predictions(
    history_days: int = Query(default=365, ge=30, le=730),
    forecast_days: int = Query(default=30, ge=1, le=180),
    allowed_term_days: int = Query(default=90, ge=1, le=365),
    limit: int = Query(default=100, ge=1, le=500),
    process_all_open: bool = Query(
        default=False,
        description="اگر true باشد تمام چک‌های دریافتی باز به‌صورت Batch بررسی می‌شوند.",
    ),
):
    from app.services.finance_prediction_service import FinancePredictionService

    try:
        return FinancePredictionService(
            history_days=history_days,
            forecast_days=forecast_days,
            allowed_term_days=allowed_term_days,
        ).cheque_return_predictions(
            limit=None if process_all_open else limit,
            batch_size=1000,
            include_all_open=process_all_open,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"پیش‌بینی ریسک برگشت چک با خطا مواجه شد: {exc}",
        ) from exc


@router.get(
    "/predictions/cash-shortage",
    summary="پیش‌بینی روزانه فشار/کسری نقدینگی",
)
def cash_shortage_prediction(
    history_days: int = Query(default=365, ge=30, le=730),
    forecast_days: int = Query(default=30, ge=1, le=180),
    opening_cash: float | None = Query(default=None, ge=0),
):
    from app.services.finance_prediction_service import FinancePredictionService

    try:
        return FinancePredictionService(
            history_days=history_days,
            forecast_days=forecast_days,
            opening_cash=opening_cash,
        ).cash_shortage_forecast()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"پیش‌بینی کسری نقدینگی با خطا مواجه شد: {exc}",
        ) from exc


@router.get(
    "/cashflow/unified",
    summary="Cash Flow واحد: موجودی Excel و خط زمان SQL",
)
def unified_cashflow(
    history_days: int = Query(default=365, ge=30, le=730),
    forecast_days: int = Query(default=30, ge=7, le=180),
    allowed_term_days: int = Query(default=90, ge=1, le=365),
):
    from app.services.unified_cashflow_service import UnifiedDailyCashflowService
    try:
        return UnifiedDailyCashflowService(
            history_days=history_days,
            forecast_days=forecast_days,
            allowed_term_days=allowed_term_days,
        ).build()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"ساخت Cash Flow واحد با خطا مواجه شد: {exc}",
        ) from exc


@router.get(
    "/cashflow/history",
    summary="مقایسه چند ماه Cash Flow واقعی Excel",
)
def cashflow_history(months: int = Query(default=6, ge=2, le=24)):
    from app.services.monthly_cashflow_excel_service import MonthlyCashflowExcelService
    return MonthlyCashflowExcelService().historical_comparison(months_limit=months)


@router.get(
    "/collection-priorities",
    summary="پیشنهاد اولویت وصول مشتریان",
)
def collection_priorities(
    history_days: int = Query(default=365, ge=30, le=730),
    forecast_days: int = Query(default=30, ge=1, le=180),
    allowed_term_days: int = Query(default=90, ge=1, le=365),
    limit: int = Query(default=25, ge=1, le=200),
):
    from app.services.finance_prediction_service import FinancePredictionService

    try:
        return FinancePredictionService(
            history_days=history_days,
            forecast_days=forecast_days,
            allowed_term_days=allowed_term_days,
        ).collection_priorities(limit=limit)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"محاسبه اولویت وصول با خطا مواجه شد: {exc}",
        ) from exc
