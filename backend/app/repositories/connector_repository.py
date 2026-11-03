from sqlalchemy.orm import Session

from app.models.datasource.connector import Connector


class ConnectorRepository:


    def create(
        self,
        db: Session,
        connector: Connector
    ):

        db.add(connector)
        db.commit()
        db.refresh(connector)

        return connector



    def get_all(
        self,
        db: Session
    ):

        return db.query(
            Connector
        ).all()