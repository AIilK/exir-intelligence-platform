from sqlalchemy.orm import Session

from app.models.datasource.connection import Connection


class ConnectionRepository:


    def create(
        self,
        db: Session,
        connection: Connection
    ):

        db.add(connection)
        db.commit()
        db.refresh(connection)

        return connection



    def get_all(
        self,
        db: Session
    ):

        return db.query(Connection).all()



    def get_by_id(
        self,
        db: Session,
        connection_id: int
    ):

        return (
            db.query(Connection)
            .filter(Connection.id == connection_id)
            .first()
        )