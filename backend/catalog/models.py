from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    ForeignKey,
    Text
)

from sqlalchemy.orm import relationship

from app.database.base import Base


class CatalogTable(Base):

    __tablename__ = "catalog_tables"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    connection_id = Column(
        Integer,
        ForeignKey("connections.id"),
        nullable=False
    )

    name = Column(
        String(255),
        nullable=False
    )

    schema_name = Column(
        String(255),
        nullable=True
    )

    description = Column(
        Text,
        nullable=True
    )

    is_active = Column(
        Boolean,
        default=True
    )

    columns = relationship(
        "CatalogColumn",
        back_populates="table",
        cascade="all, delete-orphan"
    )


class CatalogColumn(Base):

    __tablename__ = "catalog_columns"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    table_id = Column(
        Integer,
        ForeignKey("catalog_tables.id"),
        nullable=False
    )

    name = Column(
        String(255),
        nullable=False
    )

    data_type = Column(
        String(100),
        nullable=False
    )

    nullable = Column(
        Boolean,
        default=True
    )

    is_primary_key = Column(
        Boolean,
        default=False
    )

    description = Column(
        Text,
        nullable=True
    )

    business_name = Column(
        String(255),
        nullable=True
    )

    semantic_type = Column(
        String(100),
        nullable=True
    )

    table = relationship(
        "CatalogTable",
        back_populates="columns"
    )


class CatalogRelationship(Base):

    __tablename__ = "catalog_relationships"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    source_table_id = Column(
        Integer,
        ForeignKey("catalog_tables.id"),
        nullable=False
    )

    source_column_id = Column(
        Integer,
        ForeignKey("catalog_columns.id"),
        nullable=False
    )

    target_table_id = Column(
        Integer,
        ForeignKey("catalog_tables.id"),
        nullable=False
    )

    target_column_id = Column(
        Integer,
        ForeignKey("catalog_columns.id"),
        nullable=False
    )

    relationship_type = Column(
        String(50),
        default="many_to_one"
    )