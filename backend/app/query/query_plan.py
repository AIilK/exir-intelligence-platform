from typing import Any


class QueryPlanner:

    def build_plan(
        self,
        context: dict[str, Any],
    ) -> dict[str, Any]:

        tables = context.get(
            "tables",
            []
        )

        relationships = context.get(
            "relationships",
            []
        )

        return {
            "tables": [
                table["name"]
                for table in tables
            ],

            "relationships": relationships,
        }