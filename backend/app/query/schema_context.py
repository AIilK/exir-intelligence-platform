from sqlalchemy.orm import Session

from app.catalog.models import (
    CatalogTable,
    CatalogColumn,
    CatalogRelationship,
)


class SchemaContextBuilder:

    def __init__(self, db: Session):
        self.db = db

    # =====================================================
    # BUILD CONTEXT
    # =====================================================

    def build(
        self,
        connection_id: int,
        question: str,
    ) -> dict:

        # -------------------------------------------------
        # 1. پیدا کردن جدول‌های مرتبط با سؤال
        # -------------------------------------------------

        tables = (
            self.db.query(CatalogTable)
            .filter(
                CatalogTable.connection_id == connection_id,
                CatalogTable.is_active == True,
            )
            .all()
        )

        # -------------------------------------------------
        # 2. فیلتر ساده بر اساس کلمات سؤال
        # -------------------------------------------------

        question_lower = question.lower()

        matched_tables = []

        for table in tables:

            table_name = table.name.lower()

            if table_name in question_lower:
                matched_tables.append(table)

                continue

            for column in table.columns:

                if column.name.lower() in question_lower:
                    matched_tables.append(table)
                    break

        # -------------------------------------------------
        # اگر چیزی پیدا نشد، همه جدول‌ها
        # -------------------------------------------------

        if not matched_tables:
            matched_tables = tables

        # -------------------------------------------------
        # 3. ساخت اطلاعات جدول‌ها
        # -------------------------------------------------

        table_context = []

        matched_table_ids = {
            table.id
            for table in matched_tables
        }

        for table in matched_tables:

            columns = []

            for column in table.columns:

                columns.append({
                    "name": column.name,
                    "data_type": column.data_type,
                    "nullable": column.nullable,
                    "is_primary_key": column.is_primary_key,
                    "business_name": column.business_name,
                    "semantic_type": column.semantic_type,
                })

            table_context.append({
                "id": table.id,
                "name": table.name,
                "schema_name": table.schema_name,
                "columns": columns,
            })

        # -------------------------------------------------
        # 4. Relationshipها
        # -------------------------------------------------

        relationships = (
            self.db.query(CatalogRelationship)
            .all()
        )

        relationship_context = []

        for relationship in relationships:

            if (
                relationship.source_table_id
                not in matched_table_ids
                and
                relationship.target_table_id
                not in matched_table_ids
            ):
                continue

            source_table = (
                self.db.query(CatalogTable)
                .filter(
                    CatalogTable.id
                    == relationship.source_table_id
                )
                .first()
            )

            target_table = (
                self.db.query(CatalogTable)
                .filter(
                    CatalogTable.id
                    == relationship.target_table_id
                )
                .first()
            )

            source_column = (
                self.db.query(CatalogColumn)
                .filter(
                    CatalogColumn.id
                    == relationship.source_column_id
                )
                .first()
            )

            target_column = (
                self.db.query(CatalogColumn)
                .filter(
                    CatalogColumn.id
                    == relationship.target_column_id
                )
                .first()
            )

            if not all([
                source_table,
                target_table,
                source_column,
                target_column,
            ]):
                continue

            relationship_context.append({
                "source": (
                    f"{source_table.name}."
                    f"{source_column.name}"
                ),
                "target": (
                    f"{target_table.name}."
                    f"{target_column.name}"
                ),
                "relationship_type":
                    relationship.relationship_type,
            })

        # -------------------------------------------------
        # 5. خروجی نهایی
        # -------------------------------------------------

        return {
            "question": question,

            "tables": table_context,

            "relationships":
                relationship_context,
        }