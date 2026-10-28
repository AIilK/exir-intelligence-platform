from typing import Any


class SchemaPromptBuilder:

    def build(self, context: dict[str, Any]) -> str:

        question = context.get("question", "")
        tables = context.get("tables", [])
        relationships = context.get("relationships", [])

        lines = []

        # =====================================================
        # QUESTION
        # =====================================================

        lines.append("USER QUESTION:")
        lines.append(question)
        lines.append("")

        # =====================================================
        # DATABASE SCHEMA
        # =====================================================

        lines.append("DATABASE SCHEMA")
        lines.append("=" * 50)
        lines.append("")

        for table in tables:

            table_name = table.get("name")
            schema_name = table.get(
                "schema_name",
                "dbo"
            )

            lines.append(
                f"TABLE: [{schema_name}].[{table_name}]"
            )

            lines.append("COLUMNS:")

            for column in table.get("columns", []):

                name = column.get("name")
                data_type = column.get("data_type")
                nullable = column.get("nullable")
                primary_key = column.get(
                    "is_primary_key",
                    False
                )

                column_line = (
                    f"- {name}: {data_type}"
                )

                if primary_key:
                    column_line += " PRIMARY KEY"

                if not nullable:
                    column_line += " NOT NULL"

                lines.append(column_line)

            lines.append("")

        # =====================================================
        # RELATIONSHIPS
        # =====================================================

        lines.append("RELATIONSHIPS")
        lines.append("=" * 50)

        if relationships:

            for relationship in relationships:

                source = relationship.get(
                    "source"
                )

                target = relationship.get(
                    "target"
                )

                relationship_type = relationship.get(
                    "relationship_type"
                )

                lines.append(
                    f"- {source} -> {target}"
                )

                lines.append(
                    f"  TYPE: {relationship_type}"
                )

        else:

            lines.append(
                "No relationships found."
            )

        lines.append("")

        return "\n".join(lines)