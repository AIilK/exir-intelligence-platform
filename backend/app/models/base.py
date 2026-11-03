from datetime import datetime

from sqlalchemy import Column, DateTime

from app.database.base import Base


class TimestampMixin:

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )