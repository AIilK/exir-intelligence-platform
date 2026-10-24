import re
from typing import Any


class SchemaValidator:

    def validate(
        self,
        sql: str,
        context: dict[str, Any],
    ) -> dict:

        tables = context.get("tables", [])

        # =====================================================
        # 1. BUILD ALLOWED TABLES AND COLUMNS
        # =====================================================

        allowed_tables = set()
        allowed_columns = {}

        for table in tables:

            table_name = table.get("name")

            if not table_name:
                continue

            table_name_lower = table_name.lower()

            allowed_tables.add(
                table_name_lower
            )

            allowed_columns[
                table_name_lower
            ] = {
                column.get("name").lower()
                for column in table.get(
                    "columns",
                    []
                )
                if column.get("name")
            }

        # =====================================================
        # 2. VALIDATE TABLES
        # =====================================================

        table_matches = re.findall(
            r"\b(?:FROM|JOIN)\s+"
            r"(?:\[?[\w]+\]?\.)?"
            r"\[?([\w]+)\]?",
            sql,
            re.IGNORECASE,
        )

        for table_name in table_matches:

            if table_name.lower() not in allowed_tables:

                return {
                    "valid": False,
                    "reason": (
                        f"Table '{table_name}' "
                        f"is not available in schema"
                    ),
                }

        # =====================================================
        # 3. EXTRACT SELECT CLAUSE
        # =====================================================

        select_match = re.search(
            r"\bSELECT\b(.*?)\bFROM\b",
            sql,
            re.IGNORECASE | re.DOTALL,
        )

        if not select_match:

            return {
                "valid": False,
                "reason": "Could not parse SELECT clause",
            }

        select_part = select_match.group(1).strip()

        # =====================================================
        # 4. REMOVE TOP N
        # =====================================================

        select_part = re.sub(
            r"^TOP\s+(?:\(\s*)?\d+(?:\s*\))?\s*",
            "",
            select_part,
            flags=re.IGNORECASE,
        )

        select_part = select_part.strip()

        # =====================================================
        # 5. SELECT *
        # =====================================================

        if select_part == "*":

            return {
                "valid": True,
                "reason": None,
            }

        # =====================================================
        # 6. EXTRACT SELECTED COLUMNS
        # =====================================================

        selected_columns = []

        for item in select_part.split(","):

            item = item.strip()

            # -------------------------------------------------
            # Remove alias
            # -------------------------------------------------

            item = re.sub(
                r"\s+AS\s+\w+$",
                "",
                item,
                flags=re.IGNORECASE,
            )

            # -------------------------------------------------
            # Remove table prefix
            # -------------------------------------------------

            if "." in item:

                item = item.split(".")[-1]

            # -------------------------------------------------
            # Remove brackets
            # -------------------------------------------------

            item = item.strip(
                "[] "
            )

            # -------------------------------------------------
            # Ignore SQL expressions
            # -------------------------------------------------

            if (
                "(" in item
                or ")" in item
                or "*" in item
            ):
                continue

            if not item:
                continue

            selected_columns.append(
                item.lower()
            )

        # =====================================================
        # 7. VALIDATE COLUMNS
        # =====================================================

        for column in selected_columns:

            found = False

            for table_columns in allowed_columns.values():

                if column in table_columns:

                    found = True
                    break

            if not found:

                return {
                    "valid": False,
                    "reason": (
                        f"Column '{column}' "
                        f"is not available in schema"
                    ),
                }

        # =====================================================
        # 8. SUCCESS
        # =====================================================

        return {
            "valid": True,
            "reason": None,
        }