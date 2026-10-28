from pydantic import BaseModel
from typing import Optional


# =========================================================
# CATALOG IMPORT
# =========================================================

class CatalogImportRequest(BaseModel):
    connection_id: int


# =========================================================
# CATALOG TABLE
# =========================================================

class CatalogTableResponse(BaseModel):
    id: int
    connection_id: int

    name: str
    schema_name: str

    description: Optional[str] = None

    is_active: bool


# =========================================================
# CATALOG COLUMN
# =========================================================

class CatalogColumnResponse(BaseModel):
    id: int

    name: str

    data_type: str

    nullable: bool

    is_primary_key: bool


# =========================================================
# CATALOG TABLE DETAIL
# =========================================================

class CatalogTableDetailResponse(BaseModel):
    id: int

    connection_id: int

    name: str

    schema_name: str

    description: Optional[str] = None

    is_active: bool

    columns: list[CatalogColumnResponse]


# =========================================================
# CATALOG RELATIONSHIP
# =========================================================

class CatalogRelationshipResponse(BaseModel):
    id: int

    source_table_id: int

    source_column_id: int

    target_table_id: int

    target_column_id: int

    relationship_type: str


# =========================================================
# CATALOG SEARCH COLUMN
# =========================================================

class CatalogSearchColumnResponse(BaseModel):

    name: str

    data_type: str

    nullable: bool

    is_primary_key: bool


# =========================================================
# CATALOG SEARCH RELATIONSHIP
# =========================================================

class CatalogSearchRelationshipResponse(BaseModel):

    source_table: str

    source_column: str

    target_table: str

    target_column: str

    relationship_type: str


# =========================================================
# CATALOG SEARCH TABLE
# =========================================================

class CatalogSearchTableResponse(BaseModel):

    id: int

    connection_id: int

    name: str

    schema_name: str

    description: Optional[str] = None

    is_active: bool

    columns: list[CatalogSearchColumnResponse]

    relationships: list[
        CatalogSearchRelationshipResponse
    ]


# =========================================================
# CATALOG SEARCH RESPONSE
# =========================================================

class CatalogSearchResponse(BaseModel):

    query: str

    results: list[CatalogSearchTableResponse]