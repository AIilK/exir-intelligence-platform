from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from app.core.config import settings


PaymentCommitmentDecision = Literal[
    "pending_review",
    "paid",
    "cancelled",
    "still_due",
]
ALLOWED_DECISIONS = {"pending_review", "paid", "cancelled", "still_due"}
_WRITE_LOCK = Lock()


class PaymentCommitmentReviewStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(
            path or settings.payment_commitment_review_file
        ).expanduser().resolve()

    def _read_payload(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "reviews": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                "فایل تعیین‌تکلیف تعهدهای پرداخت قابل خواندن نیست."
            ) from exc
        if not isinstance(payload, dict) or not isinstance(
            payload.get("reviews"), dict
        ):
            raise RuntimeError(
                "ساختار فایل تعیین‌تکلیف تعهدهای پرداخت معتبر نیست."
            )
        return payload

    def _write_payload(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

    def all(self) -> dict[int, dict[str, Any]]:
        payload = self._read_payload()
        return {
            int(installment_id): dict(review)
            for installment_id, review in payload["reviews"].items()
        }

    def set(
        self,
        *,
        installment_id: int,
        payment_order_id: int,
        decision: str,
        note: str | None = None,
    ) -> dict[str, Any]:
        if decision not in ALLOWED_DECISIONS:
            raise ValueError(
                "decision must be pending_review, paid, cancelled, or still_due"
            )
        updated_at = datetime.now(timezone.utc).isoformat()
        clean_note = (note or "").strip() or None
        review = {
            "status": "success",
            "installment_id": int(installment_id),
            "payment_order_id": int(payment_order_id),
            "decision": decision,
            "note": clean_note,
            "updated_at": updated_at,
        }
        with _WRITE_LOCK:
            payload = self._read_payload()
            payload["reviews"][str(int(installment_id))] = {
                key: value for key, value in review.items() if key != "status"
            }
            self._write_payload(payload)
        return review
