"""API قراردادهای همکاران (ماژول contracts)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.staff_contracts import ContractError, ContractsStore, refresh_alarms_async

router = APIRouter(prefix="/finance/contracts", tags=["contracts"])


class ContractIn(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    hybrid: str | None = Field(default=None, max_length=200)
    role: str | None = Field(default=None, max_length=200)
    end_date: str | None = Field(default=None, max_length=20, description="تاریخ پایان شمسی، مثل ۱۴۰۵/۰۹/۰۱")
    note: str | None = Field(default=None, max_length=500)


@router.get("", summary="همه قراردادها با روز باقی‌مانده و وضعیت")
def list_contracts():
    return {"status": "success", **ContractsStore().summary()}


@router.post("", summary="افزودن قرارداد")
def add_contract(body: ContractIn):
    try:
        row = ContractsStore().add(body.model_dump())
    except ContractError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    refresh_alarms_async()
    return {"status": "success", "contract": row}


@router.put("/{contract_id}", summary="ویرایش یا تمدید قرارداد")
def update_contract(contract_id: int, body: ContractIn):
    try:
        row = ContractsStore().update(contract_id, body.model_dump(exclude_none=True))
    except ContractError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, detail="قرارداد پیدا نشد.") from exc
    refresh_alarms_async()
    return {"status": "success", "contract": row}


@router.delete("/{contract_id}", summary="حذف قرارداد")
def delete_contract(contract_id: int):
    try:
        ContractsStore().delete(contract_id)
    except KeyError as exc:
        raise HTTPException(404, detail="قرارداد پیدا نشد.") from exc
    refresh_alarms_async()
    return {"status": "success"}
