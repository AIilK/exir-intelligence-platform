from app.database.base import Base
from app.database.session import engine

# Models
from app.models.department import Department

from app.models.datasource.connector import Connector
from app.models.datasource.connection import Connection

from app.catalog.models import (
    CatalogTable,
    CatalogColumn,
    CatalogRelationship
)

print("Registered tables:")
print(Base.metadata.tables.keys())

Base.metadata.create_all(
    bind=engine
)

print("Database initialized successfully")