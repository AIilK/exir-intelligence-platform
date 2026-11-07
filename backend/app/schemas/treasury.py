from pydantic import BaseModel, Field


class PaymentCommitmentDecisionRequest(BaseModel):
    payment_order_id: int = Field(gt=0)
    decision: str = Field(
        pattern=r"^(pending_review|paid|cancelled|still_due)$",
        description="تصمیم انسانی خزانه برای قسط معوق",
    )
    note: str | None = Field(default=None, max_length=500)
