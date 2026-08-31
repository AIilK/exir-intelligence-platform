from sqlalchemy.orm import Session

from app.catalog.models import (
    CatalogTable,
    CatalogColumn,
    CatalogRelationship,
)

from app.catalog.repository import CatalogRepository


# =========================================================
# CATALOG SERVICE
# =========================================================

class CatalogService:

    def __init__(self):

        self.repository = CatalogRepository()

    # =====================================================
    # GET TABLES
    # =====================================================

    def get_tables(
        self,
        db: Session,
        connection_id: int | None = None,
    ):

        return self.repository.get_tables(
            db=db,
            connection_id=connection_id,
        )

    # =====================================================
    # GET TABLE
    # =====================================================

    def get_table(
        self,
        db: Session,
        table_id: int,
    ):

        return self.repository.get_table_by_id(
            db=db,
            table_id=table_id,
        )

    # =====================================================
    # GET COLUMNS
    # =====================================================

    def get_columns(
        self,
        db: Session,
        table_id: int,
    ):

        return self.repository.get_columns(
            db=db,
            table_id=table_id,
        )

    # =====================================================
    # GET RELATIONSHIPS
    # =====================================================

    def get_relationships(
        self,
        db: Session,
        connection_id: int | None = None,
    ):

        return self.repository.get_relationships(
            db=db,
            connection_id=connection_id,
        )

    # =====================================================
    # IMPORT SQL SERVER SCHEMA
    # =====================================================

    def import_sqlserver_schema(
        self,
        db: Session,
        connection_id: int,
        config: dict,
    ):

        sync_service = CatalogSyncService()

        return sync_service.sync_sqlserver_schema(
            db=db,
            connection_id=connection_id,
            config=config,
        )


# =========================================================
# CATALOG SYNC SERVICE
# =========================================================

class CatalogSyncService:

    def __init__(self):

        self.repository = CatalogRepository()

    # =====================================================
    # SYNC SQL SERVER SCHEMA
    # =====================================================

    def sync_sqlserver_schema(
        self,
        db: Session,
        connection_id: int,
        config: dict,
    ):
        """
        این متد:

        1. به SQL Server متصل می‌شود
        2. Schema را دریافت می‌کند
        3. جدول‌ها را Sync می‌کند
        4. ستون‌ها را Sync می‌کند
        5. Primary Keyها را Sync می‌کند
        6. Foreign Keyها را Sync می‌کند
        7. Relationshipها را ایجاد می‌کند
        """

        # =================================================
        # 1. IMPORT SQL SERVER CONNECTOR
        # =================================================

        from app.integrations.sqlserver_connector import (
            SQLServerConnector
        )

        # =================================================
        # 2. CREATE CONNECTOR
        # =================================================

        connector = SQLServerConnector(
            config
        )

        # =================================================
        # 3. GET SCHEMA FROM SQL SERVER
        # =================================================

        result = connector.get_schema()

        if not result["success"]:

            raise Exception(
                result.get(
                    "error",
                    "Failed to get SQL Server schema"
                )
            )

        # =================================================
        # 4. SYNC SCHEMA
        # =================================================

        return self.sync_schema(
            db=db,
            connection_id=connection_id,
            schema_data=result,
        )

    # =====================================================
    # SYNC SCHEMA INTO CATALOG
    # =====================================================

    def sync_schema(
        self,
        db: Session,
        connection_id: int,
        schema_data: dict,
    ):
        """
        Schema دریافت شده از SQL Server را
        داخل Catalog ذخیره و به‌روزرسانی می‌کند.
        """

        # =================================================
        # STATISTICS
        # =================================================

        imported_tables = 0
        imported_columns = 0
        imported_relationships = 0

        updated_tables = 0
        updated_columns = 0

        # =================================================
        # GET SCHEMA
        # =================================================

        schema = schema_data.get(
            "schema",
            {}
        )

        # =================================================
        # MAPS
        # =================================================

        table_map = {}
        column_map = {}

        # =================================================
        # 1. SYNC TABLES
        # =================================================

        for table_name, table_info in schema.items():

            schema_name = table_info.get(
                "schema_name",
                "dbo",
            )

            # -------------------------------------------------
            # پیدا کردن جدول موجود
            # -------------------------------------------------

            catalog_table = (
                self.repository.get_table(
                    db=db,
                    connection_id=connection_id,
                    table_name=table_name,
                )
            )

            # -------------------------------------------------
            # جدول جدید
            # -------------------------------------------------

            if catalog_table is None:

                catalog_table = CatalogTable(
                    connection_id=connection_id,
                    name=table_name,
                    schema_name=schema_name,
                    is_active=True,
                )

                db.add(catalog_table)

                db.flush()

                imported_tables += 1

            # -------------------------------------------------
            # جدول موجود
            # -------------------------------------------------

            else:

                changed = False

                # Schema name
                if (
                    catalog_table.schema_name
                    != schema_name
                ):

                    catalog_table.schema_name = (
                        schema_name
                    )

                    changed = True

                # Active
                if not catalog_table.is_active:

                    catalog_table.is_active = True

                    changed = True

                if changed:

                    updated_tables += 1

            # -------------------------------------------------
            # ذخیره در Map
            # -------------------------------------------------

            table_map[table_name] = catalog_table

        # =================================================
        # 2. SYNC COLUMNS
        # =================================================

        for table_name, table_info in schema.items():

            catalog_table = table_map[
                table_name
            ]

            # -------------------------------------------------
            # Primary Keys
            # -------------------------------------------------

            primary_keys = set(
                table_info.get(
                    "primary_keys",
                    [],
                )
            )

            # -------------------------------------------------
            # Columns
            # -------------------------------------------------

            for column_info in table_info.get(
                "columns",
                [],
            ):

                column_name = column_info[
                    "name"
                ]

                # ---------------------------------------------
                # آیا Primary Key است؟
                # ---------------------------------------------

                is_primary_key = (
                    column_name
                    in primary_keys
                )

                # ---------------------------------------------
                # پیدا کردن Column موجود
                # ---------------------------------------------

                existing_column = (
                    db.query(
                        CatalogColumn
                    )
                    .filter(
                        CatalogColumn.table_id
                        == catalog_table.id,

                        CatalogColumn.name
                        == column_name,
                    )
                    .first()
                )

                # ---------------------------------------------
                # Column جدید
                # ---------------------------------------------

                if existing_column is None:

                    column = CatalogColumn(

                        table_id=
                        catalog_table.id,

                        name=
                        column_name,

                        data_type=
                        column_info["type"],

                        nullable=
                        column_info["nullable"],

                        is_primary_key=
                        is_primary_key,
                    )

                    db.add(column)

                    db.flush()

                    imported_columns += 1

                # ---------------------------------------------
                # Column موجود
                # ---------------------------------------------

                else:

                    column = existing_column

                    changed = False

                    # Data Type
                    new_type = (
                        column_info["type"]
                    )

                    if (
                        column.data_type
                        != new_type
                    ):

                        column.data_type = (
                            new_type
                        )

                        changed = True

                    # Nullable
                    new_nullable = (
                        column_info["nullable"]
                    )

                    if (
                        column.nullable
                        != new_nullable
                    ):

                        column.nullable = (
                            new_nullable
                        )

                        changed = True

                    # Primary Key
                    if (
                        column.is_primary_key
                        != is_primary_key
                    ):

                        column.is_primary_key = (
                            is_primary_key
                        )

                        changed = True

                    if changed:

                        updated_columns += 1

                # ---------------------------------------------
                # ذخیره در Column Map
                # ---------------------------------------------

                column_map[
                    (
                        table_name,
                        column_name,
                    )
                ] = column

        # =================================================
        # 3. SYNC RELATIONSHIPS
        # =================================================

        for table_name, table_info in schema.items():

            foreign_keys = table_info.get(
                "foreign_keys",
                [],
            )

            for fk in foreign_keys:

                # ---------------------------------------------
                # Source Column
                # ---------------------------------------------

                source_column = column_map.get(
                    (
                        table_name,
                        fk["column"],
                    )
                )

                # ---------------------------------------------
                # Target Column
                # ---------------------------------------------

                target_column = column_map.get(
                    (
                        fk["references_table"],
                        fk["references_column"],
                    )
                )

                # ---------------------------------------------
                # اگر Column پیدا نشد
                # ---------------------------------------------

                if (
                    source_column is None
                    or target_column is None
                ):

                    continue

                # ---------------------------------------------
                # بررسی Relationship تکراری
                # ---------------------------------------------

                existing_relationship = (
                    db.query(
                        CatalogRelationship
                    )
                    .filter(

                        CatalogRelationship
                        .source_column_id
                        == source_column.id,

                        CatalogRelationship
                        .target_column_id
                        == target_column.id,
                    )
                    .first()
                )

                if existing_relationship:

                    continue

                # ---------------------------------------------
                # ایجاد Relationship
                # ---------------------------------------------

                relationship = CatalogRelationship(

                    source_table_id=
                    source_column.table_id,

                    source_column_id=
                    source_column.id,

                    target_table_id=
                    target_column.table_id,

                    target_column_id=
                    target_column.id,

                    relationship_type=
                    "many_to_one",
                )

                db.add(
                    relationship
                )

                imported_relationships += 1

        # =================================================
        # 4. COMMIT
        # =================================================

        db.commit()

        # =================================================
        # 5. RESULT
        # =================================================

        return {

            "success": True,

            "database":
                schema_data.get(
                    "database"
                ),

            "tables_imported":
                imported_tables,

            "columns_imported":
                imported_columns,

            "relationships_imported":
                imported_relationships,

            "tables_updated":
                updated_tables,

            "columns_updated":
                updated_columns,
        }
