from sqlalchemy.orm import Session

from app.repositories.connection_repository import ConnectionRepository

from app.integrations.factory import ConnectorFactory


class DatasourceManager:

    def __init__(self):

        self.connection_repo = ConnectionRepository()


    def get_connector(
        self,
        db: Session,
        connection_id: int
    ):

        connection = self.connection_repo.get_by_id(
            db,
            connection_id
        )

        if connection is None:

            raise Exception("Connection not found")

        connector = ConnectorFactory.create(

            connector.connector_type,

            connection.connection_config

        )

        return connector