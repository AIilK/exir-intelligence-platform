from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db

from app.catalog.schemas import (
    CatalogImportRequest,
    CatalogTableResponse,
    CatalogTableDetailResponse,
    CatalogRelationshipResponse,
    CatalogSearchResponse,
)

from app.catalog.service import CatalogService

from app.catalog.repository import CatalogRepository

from app.models.datasource.connection import Connection


router = APIRouter(
    prefix="/catalog",
    tags=["Catalog"]
)


# =========================================================
# IMPORT SQL SERVER SCHEMA
# =========================================================

@router.post(
    "/import/sqlserver"
)
def import_sqlserver_schema(
    data: CatalogImportRequest,
    db: Session = Depends(get_db)
):

    connection = (
        db.query(Connection)
        .filter(
            Connection.id == data.connection_id
        )
        .first()
    )

    if connection is None:

        raise HTTPException(
            status_code=404,
            detail="Connection not found"
        )

    config = connection.connection_config

    service = CatalogService()

    try:

        result = service.import_sqlserver_schema(
            db=db,
            connection_id=connection.id,
            config=config
        )

        return result

    except Exception as e:

        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# =========================================================
# GET CATALOG TABLES
# =========================================================

@router.get(
    "/tables",
    response_model=list[CatalogTableResponse]
)
def get_catalog_tables(
    connection_id: int | None = None,
    db: Session = Depends(get_db)
):

    repository = CatalogRepository()

    tables = repository.get_tables(
        db=db,
        connection_id=connection_id
    )

    return tables


# =========================================================
# GET CATALOG TABLE DETAIL
# =========================================================

@router.get(
    "/tables/{table_id}",
    response_model=CatalogTableDetailResponse
)
def get_catalog_table(
    table_id: int,
    db: Session = Depends(get_db)
):

    repository = CatalogRepository()

    table = repository.get_table_by_id(
        db=db,
        table_id=table_id
    )

    if table is None:

        raise HTTPException(
            status_code=404,
            detail="Catalog table not found"
        )

    columns = repository.get_columns(
        db=db,
        table_id=table.id
    )

    return {
        "id": table.id,
        "connection_id": table.connection_id,
        "name": table.name,
        "schema_name": table.schema_name,
        "description": table.description,
        "is_active": table.is_active,
        "columns": columns
    }


# =========================================================
# GET CATALOG RELATIONSHIPS
# =========================================================

@router.get(
    "/relationships",
    response_model=list[CatalogRelationshipResponse]
)
def get_catalog_relationships(
    connection_id: int | None = None,
    db: Session = Depends(get_db)
):

    repository = CatalogRepository()

    relationships = repository.get_relationships(
        db=db,
        connection_id=connection_id
    )

    return relationships


# =========================================================
# SYNC SQL SERVER SCHEMA
# =========================================================

@router.post(
    "/sync/sqlserver"
)
def sync_sqlserver_schema(
    request: CatalogImportRequest,
    db: Session = Depends(get_db)
):

    connection = (
        db.query(Connection)
        .filter(
            Connection.id == request.connection_id
        )
        .first()
    )

    if connection is None:

        raise HTTPException(
            status_code=404,
            detail="Connection not found"
        )

    service = CatalogService()

    try:

        result = service.import_sqlserver_schema(
            db=db,
            connection_id=connection.id,
            config=connection.connection_config
        )

        return result

    except Exception as e:

        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# =========================================================
# SEARCH CATALOG
# =========================================================

@router.get(
    "/search",
    response_model=CatalogSearchResponse
)
def search_catalog(
    q: str,
    connection_id: int | None = None,
    db: Session = Depends(get_db)
):

    if not q.strip():

        raise HTTPException(
            status_code=400,
            detail="Search query cannot be empty"
        )

    repository = CatalogRepository()

    results = repository.search_catalog(
        db=db,
        query=q,
        connection_id=connection_id
    )

    formatted_results = []

    for item in results:

        table = item["table"]

        columns = []

        for column in item["columns"]:

            columns.append(
                {
                    "name": column.name,
                    "data_type": column.data_type,
                    "nullable": column.nullable,
                    "is_primary_key": column.is_primary_key
                }
            )

        formatted_results.append(
            {
                "id": table.id,
                "connection_id": table.connection_id,
                "name": table.name,
                "schema_name": table.schema_name,
                "description": table.description,
                "is_active": table.is_active,
                "columns": columns,
                "relationships": item[
                    "relationships"
                ]
            }
        )

    return {
        "query": q,
        "results": formatted_results
    }