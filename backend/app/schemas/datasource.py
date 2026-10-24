from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


# =========================================================
# Connector
# =========================================================

class ConnectorCreate(BaseModel):
    name: str
    connector_type: str
    description: str | None = None


class ConnectorResponse(BaseModel):
    id: int
    name: str
    connector_type: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =========================================================
# Connection
# =========================================================

class ConnectionCreate(BaseModel):
    name: str
    connector_id: int
    description: str | None = None
    connection_config: dict[str, Any]


class ConnectionResponse(BaseModel):
    id: int
    name: str
    connector_id: int
    description: str | None
    connection_config: dict[str, Any]
    is_active: bool

    model_config = ConfigDict(from_attributes=True)