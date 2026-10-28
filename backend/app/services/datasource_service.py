from sqlalchemy.orm import Session

from app.models.datasource.connector import Connector
from app.models.datasource.connection import Connection

from app.repositories.connector_repository import ConnectorRepository
from app.repositories.connection_repository import ConnectionRepository


class DatasourceService:

    def __init__(self):

        self.connector_repo = ConnectorRepository()

        self.connection_repo = ConnectionRepository()


    # -------------------------
    # Connector
    # -------------------------

    def create_connector(
        self,
        db: Session,
        data
    ):

        connector = Connector(
            name=data.name,
            connector_type=data.connector_type,
            description=data.description
        )

        return self.connector_repo.create(
            db,
            connector
        )


    def get_connectors(
        self,
        db: Session
    ):

        return self.connector_repo.get_all(db)


    def create_connection(
        self,
        db: Session,
        data
    ):

        connection = Connection(
            name=data.name,
            connector_id=data.connector_id,
            description=data.description,
            connection_config=data.connection_config
        )

        return self.connection_repo.create(
            db,
            connection
        )


    def get_connections(
        self,
        db: Session
    ):

        return self.connection_repo.get_all(db)



    def get_connection(
        self,
        db: Session,
        connection_id: int
    ):

        return self.connection_repo.get_by_id(
            db,
            connection_id
        )



    def update_connection(
        self,
        db: Session,
        connection
    ):

        return self.connection_repo.update(
            db,
            connection
        )



    def delete_connection(
        self,
        db: Session,
        connection
    ):

        return self.connection_repo.delete(
            db,
            connection
        )
    def get_connections(
        self,
        db: Session
    ):

        return self.connection_repo.get_all(db)