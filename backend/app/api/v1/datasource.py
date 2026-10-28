from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.schemas.datasource import ConnectionCreate
from app.services.datasource_service import DatasourceService
from app.schemas.datasource import ConnectionResponse

router = APIRouter(
    prefix="/datasource",
    tags=["Datasource"]
)


service = DatasourceService()

@router.get(
    "/connections",
    response_model=list[ConnectionResponse]
)
def get_connections(
    db: Session = Depends(get_db)
):

    service = DatasourceService()

    return service.get_connections(db)

@router.post("/connections")
def create_connection(
    data: ConnectionCreate,
    db: Session = Depends(get_db)
):

    return service.create_connection(
        db,
        data
    )


