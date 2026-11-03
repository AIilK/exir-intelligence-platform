from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.catalog.models import (
    CatalogTable,
    CatalogColumn,
    CatalogRelationship,
)


class CatalogRepository:

    # =====================================================
    # GET TABLES
    # =====================================================

    def get_tables(
        self,
        db: Session,
        connection_id: int | None = None,
    ):

        query = db.query(
            CatalogTable
        )

        if connection_id is not None:

            query = query.filter(
                CatalogTable.connection_id
                == connection_id
            )

        return (
            query
            .filter(
                CatalogTable.is_active == True
            )
            .order_by(
                CatalogTable.id
            )
            .all()
        )

    # =====================================================
    # GET TABLE BY ID
    # =====================================================

    def get_table_by_id(
        self,
        db: Session,
        table_id: int,
    ):

        return (
            db.query(CatalogTable)
            .filter(
                CatalogTable.id
                == table_id
            )
            .first()
        )

    # =====================================================
    # GET TABLE
    # =====================================================

    def get_table(
        self,
        db: Session,
        connection_id: int,
        table_name: str,
    ):

        return (
            db.query(CatalogTable)
            .filter(
                CatalogTable.connection_id
                == connection_id,

                CatalogTable.name
                == table_name,

                CatalogTable.is_active
                == True,
            )
            .first()
        )

    # =====================================================
    # GET COLUMNS
    # =====================================================

    def get_columns(
        self,
        db: Session,
        table_id: int,
    ):

        return (
            db.query(CatalogColumn)
            .filter(
                CatalogColumn.table_id
                == table_id
            )
            .order_by(
                CatalogColumn.id
            )
            .all()
        )

    # =====================================================
    # GET COLUMN BY ID
    # =====================================================

    def get_column_by_id(
        self,
        db: Session,
        column_id: int,
    ):

        return (
            db.query(CatalogColumn)
            .filter(
                CatalogColumn.id
                == column_id
            )
            .first()
        )

    # =====================================================
    # GET RELATIONSHIPS
    # =====================================================

    def get_relationships(
        self,
        db: Session,
        connection_id: int | None = None,
    ):

        query = (
            db.query(
                CatalogRelationship
            )
        )

        if connection_id is not None:

            query = (
                query
                .join(
                    CatalogTable,
                    CatalogRelationship
                    .source_table_id
                    == CatalogTable.id,
                )
                .filter(
                    CatalogTable.connection_id
                    == connection_id
                )
            )

        return query.all()

    # =====================================================
    # GET RELATIONSHIPS FOR TABLE
    # =====================================================

    def get_relationships_for_table(
        self,
        db: Session,
        table_id: int,
    ):

        return (
            db.query(
                CatalogRelationship
            )
            .filter(
                or_(
                    CatalogRelationship
                    .source_table_id
                    == table_id,

                    CatalogRelationship
                    .target_table_id
                    == table_id,
                )
            )
            .all()
        )

    # =====================================================
    # SEARCH TABLES
    # =====================================================

    def search_tables(
        self,
        db: Session,
        connection_id: int,
        query: str,
    ):

        search_text = (
            query.strip().lower()
        )

        tables = (
            db.query(CatalogTable)
            .filter(
                CatalogTable.connection_id
                == connection_id,

                CatalogTable.is_active
                == True,
            )
            .all()
        )

        results = []

        for table in tables:

            table_name = (
                table.name.lower()
            )

            if (
                search_text
                in table_name
                or table_name
                in search_text
            ):

                results.append(
                    table
                )

                continue

            columns = self.get_columns(
                db=db,
                table_id=table.id,
            )

            for column in columns:

                column_name = (
                    column.name.lower()
                )

                if (
                    search_text
                    in column_name
                ):

                    results.append(
                        table
                    )

                    break

        return results

    # =====================================================
    # SEARCH TABLES WITH COLUMNS
    # =====================================================

    def search_tables_with_columns(
        self,
        db: Session,
        connection_id: int,
        query: str,
    ):

        search_text = (
            query.strip().lower()
        )

        tables = (
            db.query(CatalogTable)
            .filter(
                CatalogTable.connection_id
                == connection_id,

                CatalogTable.is_active
                == True,
            )
            .all()
        )

        results = []

        for table in tables:

            columns = self.get_columns(
                db=db,
                table_id=table.id,
            )

            table_name = (
                table.name.lower()
            )

            # -----------------------------------------
            # TABLE MATCH
            # -----------------------------------------

            table_match = (
                search_text
                in table_name
                or table_name
                in search_text
            )

            # -----------------------------------------
            # COLUMN MATCH
            # -----------------------------------------

            column_match = False

            for column in columns:

                column_name = (
                    column.name.lower()
                )

                if (
                    search_text
                    in column_name
                ):

                    column_match = True

                    break

            # -----------------------------------------
            # CUSTOMER KEYWORDS
            # -----------------------------------------

            customer_match = False

            if (
                "مشتری"
                in query
                or "مشتریان"
                in query
                or "مشتری‌ها"
                in query
                or "customer"
                in search_text
                or "customers"
                in search_text
            ):

                customer_match = (
                    table_name
                    in [
                        "customer",
                        "customers",
                    ]
                )

            # -----------------------------------------
            # ADD TABLE
            # -----------------------------------------

            if (
                table_match
                or column_match
                or customer_match
            ):

                results.append({

                    "id": table.id,

                    "connection_id":
                        table.connection_id,

                    "name":
                        table.name,

                    "schema_name":
                        table.schema_name,

                    "description":
                        table.description,

                    "is_active":
                        table.is_active,

                    "columns": [

                        {
                            "name":
                                column.name,

                            "data_type":
                                column.data_type,

                            "nullable":
                                column.nullable,

                            "is_primary_key":
                                column.is_primary_key,
                        }

                        for column
                        in columns
                    ],
                })

        return results