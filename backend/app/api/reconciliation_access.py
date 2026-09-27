from secrets import compare_digest

from fastapi import Header, HTTPException, status

from app.core.config import settings


def require_reconciliation_api_key(
    x_reconciliation_api_key: str | None = Header(default=None),
) -> None:
    """Fail closed: reconciliation files/results are never anonymously exposed."""

    configured = settings.reconciliation_api_key.strip()
    provided = (x_reconciliation_api_key or "").strip()
    if not configured or not provided or not compare_digest(configured, provided):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="دسترسی به سرویس مغایرت‌گیری مجاز نیست.",
        )
