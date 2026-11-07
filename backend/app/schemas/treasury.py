from pydantic import BaseModel, Field


class AccountBalance(BaseModel):

    id:int
    name:str
    number:str | None
    balance:float
    debit:float
    credit:float


class FinancialQueryRequest(BaseModel):
    question: str = Field(
        min_length=3,
        max_length=1000,
        description="سؤال آزاد مالی برای تولید و اجرای SQL فقط‌خواندنی",
        examples=["در ۳۰ روز گذشته بیشترین پرداخت به کدام طرف حساب بوده است؟"],
    )


class PaymentCommitmentDecisionRequest(BaseModel):
    payment_order_id: int = Field(gt=0)
    decision: str = Field(
        pattern=r"^(pending_review|paid|cancelled|still_due)$",
        description="تصمیم انسانی خزانه برای قسط معوق",
    )
    note: str | None = Field(default=None, max_length=500)
