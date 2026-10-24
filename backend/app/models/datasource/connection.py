from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    JSON,
    ForeignKey
)

from sqlalchemy.orm import relationship

from app.database.base import Base


class Connection(Base):

    __tablename__ = "connections"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    name = Column(
        String(100),
        nullable=False
    )

    connector_id = Column(
        Integer,
        ForeignKey("connectors.id"),
        nullable=False
    )

    description = Column(
        Text,
        nullable=True
    )

    connection_config = Column(
        JSON,
        nullable=False
    )

    is_active = Column(
        Boolean,
        default=True
    )

    connector = relationship(
        "Connector",
        back_populates="connections"
    )