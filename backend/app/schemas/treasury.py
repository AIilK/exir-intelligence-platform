from pydantic import BaseModel, Field


class AccountBalance(BaseModel):

    id:int
    name:str
    number:str | None
    balance:float
    debit:float
    credit:float


class TreasuryChatRequest(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=2000,
        description="سؤال فارسی کاربر از Agent خزانه",
        examples=["مانده حساب ابرام چقدر است؟"],
    )
    session_id: str | None = Field(
        default=None,
        min_length=8,
        max_length=100,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="شناسه مکالمه؛ در پیام اول اختیاری و برای ادامه گفتگو الزامی است",
    )


class TreasuryChatResponse(BaseModel):
    status: str
    answer: str
    session_id: str


class TreasuryChatStatusResponse(BaseModel):
    status: str
    ready: bool
    model: str
    message: str
    diagnostics: dict[str, str]


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
