from pydantic import BaseModel, Field


class FinanceDashboardPolicy(BaseModel):
    allowed_term_days: int = Field(default=90, ge=1, le=365)
