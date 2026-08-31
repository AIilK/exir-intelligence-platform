from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.query.schemas import (
    QueryAskRequest,
    QueryAskResponse,
    QueryExecuteRequest,
    QueryExecuteResponse,
    QueryPlanRequest,
    QueryPlanResponse,
    SQLGenerateRequest,
    SQLGenerateResponse,
)
from app.query.service import QueryService


router = APIRouter(prefix="/query", tags=["Query"])


@router.post("/plan", response_model=QueryPlanResponse)
def create_query_plan(request: QueryPlanRequest, db: Session = Depends(get_db)):
    try:
        return QueryService().build_query_plan(
            db=db,
            connection_id=request.connection_id,
            question=request.question,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/generate-sql", response_model=SQLGenerateResponse)
def generate_sql(request: SQLGenerateRequest, db: Session = Depends(get_db)):
    try:
        return QueryService().generate_sql(
            db=db,
            connection_id=request.connection_id,
            question=request.question,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/execute", response_model=QueryExecuteResponse)
def execute_query(request: QueryExecuteRequest, db: Session = Depends(get_db)):
    result = QueryService().execute_sql(
        db=db,
        connection_id=request.connection_id,
        sql=request.sql,
    )
    if not result["success"]:
        code = 404 if result.get("error") == "Connection not found" else 400
        raise HTTPException(status_code=code, detail=result.get("error"))
    return result


@router.post("/ask", response_model=QueryAskResponse)
def ask_question(request: QueryAskRequest, db: Session = Depends(get_db)):
    result = QueryService().execute_question(
        db=db,
        connection_id=request.connection_id,
        question=request.question,
    )
    if not result["success"] and result.get("error") == "Connection not found":
        raise HTTPException(status_code=404, detail=result["error"])
    return result
