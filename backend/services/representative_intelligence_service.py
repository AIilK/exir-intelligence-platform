from __future__ import annotations

import csv
import io
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import settings


class RepresentativeIntelligenceService:
    """Aggregates customer intelligence by representative using an explicit mapping.

    The mapping is deliberately external until KarAmand's real representative table
    and customer key are confirmed. This prevents silently assigning a customer to
    the wrong representative.
    """

    def __init__(self, mapping_file: str | None = None):
        self.mapping_file = Path(mapping_file or settings.customer_representative_mapping_file)

    def aggregate(self, customers: list[dict[str, Any]]) -> dict[str, Any]:
        mapping = self._load_mapping()
        if not mapping:
            return {
                "status": "not_ready",
                "reason": "representative_mapping_missing",
                "message": "ارتباط مشتری و نماینده هنوز تنظیم نشده است.",
                "required_columns": ["counterpart_ref", "representative_id", "representative_name"],
                "mapping_file": str(self.mapping_file),
                "representatives": [],
            }
        groups: dict[str, dict[str, Any]] = {}
        unmapped = 0
        for customer in customers:
            ref = str(customer.get("counterpart_ref"))
            rep = mapping.get(ref)
            if not rep:
                unmapped += 1
                continue
            key = rep["representative_id"]
            row = groups.setdefault(key, {
                **rep, "customer_count": 0, "high_risk_customer_count": 0,
                "open_exposure": 0.0, "overdue_open_amount": 0.0,
                "expected_collection_amount": 0.0, "collection_gap": 0.0,
                "risk_score_sum": 0.0, "customers": [],
            })
            row["customer_count"] += 1
            row["high_risk_customer_count"] += int(customer.get("risk_level") == "high")
            for field in ("open_exposure", "overdue_open_amount", "expected_collection_amount", "collection_gap"):
                row[field] += float(customer.get(field, 0) or 0)
            row["risk_score_sum"] += float(customer.get("risk_score", 0) or 0)
            row["customers"].append({
                "counterpart_ref": customer.get("counterpart_ref"),
                "counterpart_name": customer.get("counterpart_name"),
                "risk_score": customer.get("risk_score"),
                "risk_level": customer.get("risk_level"),
            })
        result = []
        for row in groups.values():
            row["average_risk_score"] = round(row.pop("risk_score_sum") / max(row["customer_count"], 1), 1)
            row["status"] = "critical" if row["high_risk_customer_count"] else "attention" if row["average_risk_score"] >= 30 else "good"
            row["human_analysis"] = self._explain(row)
            result.append(row)
        result.sort(key=lambda x: (x["high_risk_customer_count"], x["average_risk_score"], x["open_exposure"]), reverse=True)
        return {"status": "success", "representatives": result, "count": len(result), "unmapped_customer_count": unmapped}

    @staticmethod
    def build_template(customers: list[dict[str, Any]]) -> str:
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "counterpart_ref",
                "counterpart_code",
                "counterpart_name",
                "representative_id",
                "representative_name",
            ],
        )
        writer.writeheader()
        for customer in customers:
            writer.writerow({
                "counterpart_ref": customer.get("counterpart_ref", ""),
                "counterpart_code": customer.get("counterpart_code", ""),
                "counterpart_name": customer.get("counterpart_name", ""),
                "representative_id": "",
                "representative_name": "",
            })
        return "\ufeff" + stream.getvalue()

    def save_mapping(self, content: bytes, valid_refs: set[str]) -> dict[str, Any]:
        if len(content) > 2 * 1024 * 1024:
            raise ValueError("حجم فایل Mapping نباید بیشتر از ۲ مگابایت باشد.")
        try:
            decoded = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("فایل CSV باید با UTF-8 ذخیره شده باشد.") from exc
        reader = csv.DictReader(io.StringIO(decoded))
        required = {"counterpart_ref", "representative_id", "representative_name"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError("ستون‌های counterpart_ref، representative_id و representative_name الزامی هستند.")

        clean_rows: list[dict[str, str]] = []
        seen: set[str] = set()
        invalid_refs: list[str] = []
        for index, row in enumerate(reader, start=2):
            ref = str(row.get("counterpart_ref") or "").strip()
            rep_id = str(row.get("representative_id") or "").strip()
            rep_name = str(row.get("representative_name") or "").strip()
            if not ref and not rep_id and not rep_name:
                continue
            if not ref or not rep_id or not rep_name:
                raise ValueError(f"ردیف {index}: شناسه مشتری، شناسه نماینده و نام نماینده باید کامل باشند.")
            if ref not in valid_refs:
                invalid_refs.append(ref)
                continue
            if ref in seen:
                raise ValueError(f"طرف حساب {ref} بیش از یک‌بار در فایل تکرار شده است.")
            seen.add(ref)
            clean_rows.append({
                "counterpart_ref": ref,
                "representative_id": rep_id,
                "representative_name": rep_name,
            })
        if invalid_refs:
            raise ValueError("شناسه طرف حساب نامعتبر است: " + "، ".join(invalid_refs[:10]))
        if not clean_rows:
            raise ValueError("هیچ Mapping کامل و معتبری در فایل وجود ندارد.")

        self.mapping_file.parent.mkdir(parents=True, exist_ok=True)
        backup = None
        if self.mapping_file.exists():
            backup = self.mapping_file.with_suffix(
                f".{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak.csv"
            )
            shutil.copy2(self.mapping_file, backup)
        temp = self.mapping_file.with_suffix(".tmp")
        with temp.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=["counterpart_ref", "representative_id", "representative_name"],
            )
            writer.writeheader()
            writer.writerows(clean_rows)
        temp.replace(self.mapping_file)
        return {
            "status": "success",
            "mapped_customer_count": len(clean_rows),
            "representative_count": len({row["representative_id"] for row in clean_rows}),
            "mapping_file": str(self.mapping_file),
            "backup_created": bool(backup),
        }

    def _load_mapping(self) -> dict[str, dict[str, str]]:
        if not self.mapping_file.exists():
            return {}
        with self.mapping_file.open("r", encoding="utf-8-sig", newline="") as stream:
            rows = csv.DictReader(stream)
            return {
                str(row["counterpart_ref"]).strip(): {
                    "representative_id": str(row["representative_id"]).strip(),
                    "representative_name": str(row["representative_name"]).strip(),
                }
                for row in rows if row.get("counterpart_ref") and row.get("representative_id")
            }

    @staticmethod
    def _explain(row: dict[str, Any]) -> str:
        if row["status"] == "critical":
            return f"این نماینده {row['high_risk_customer_count']} مشتری پرریسک دارد و باید پرونده‌های وصول آن در اولویت بررسی قرار گیرد."
        if row["status"] == "attention":
            return "میانگین ریسک مشتریان این نماینده نیازمند توجه و پایش هفتگی است."
        return "رفتار مالی مشتریان این نماینده در محدوده قابل قبول قرار دارد."
