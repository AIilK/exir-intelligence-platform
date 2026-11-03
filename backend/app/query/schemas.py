from pydantic import BaseModel


class QueryPlanRequest(BaseModel):
    connection_id: int
    question: str


class QueryRelationship(BaseModel):
    source: str
    target: str
    relationship_type: str


class QueryPlanResponse(BaseModel):
    success: bool
    question: str
    tables: list[str]
    relationships: list[QueryRelationship]
    error: str | None = None


class QueryExecuteRequest(BaseModel):
    connection_id: int
    sql: str


class QueryExecuteResponse(BaseModel):
    success: bool
    columns: list[str]
    rows: list[dict]
    row_count: int
    error: str | None = None


class SQLGenerateRequest(BaseModel):
    connection_id: int
    question: str


class SQLGenerateResponse(BaseModel):
    success: bool
    question: str
    sql: str
    error: str | None = None


class QueryAskRequest(BaseModel):
    connection_id: int
    question: str


class QueryAskResponse(BaseModel):
    success: bool
    question: str
    sql: str
    columns: list[str]
    rows: list[dict]
    row_count: int
    error: str | None = None
