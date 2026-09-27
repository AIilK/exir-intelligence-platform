from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    Text
)

from sqlalchemy.orm import relationship

from app.database.base import Base
from app.models.base import TimestampMixin


class Connector(Base, TimestampMixin):

    __tablename__ = "connectors"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    name = Column(
        String(100),
        nullable=False,
        unique=True
    )

    connector_type = Column(
        String(50),
        nullable=False
    )

    description = Column(
        Text,
        nullable=True
    )

    is_active = Column(
        Boolean,
        default=True
    )

    connections = relationship(
        "Connection",
        back_populates="connector"
    )