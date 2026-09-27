import re
from typing import Any

from app.integrations.sqlserver_connector import SQLServerConnector


class QueryExecutor:

    def __init__(self, config: dict[str, Any]):
        self.config = config

    # =====================================================
    # VALIDATE SQL
    # =====================================================

    def validate_sql(self, sql: str) -> None:
        """
        فقط اجرای SELECT را اجازه می‌دهد.
        دستورات INSERT / UPDATE / DELETE / DROP / ALTER / etc
        مجاز نیستند.
        """

        if not sql or not sql.strip():
            raise ValueError("SQL query is empty")

        query = sql.strip()

        # حذف ; انتهایی
        query = query.rstrip(";").strip()

        # فقط یک Statement
        if ";" in query:
            raise ValueError(
                "Multiple SQL statements are not allowed"
            )

        # باید با SELECT شروع شود
        if not re.match(
            r"^SELECT\b",
            query,
            re.IGNORECASE,
        ):
            raise ValueError(
                "Only SELECT queries are allowed"
            )

        # دستورات خطرناک
        forbidden_keywords = [
            "INSERT",
            "UPDATE",
            "DELETE",
            "DROP",
            "ALTER",
            "TRUNCATE",
            "CREATE",
            "EXEC",
            "EXECUTE",
            "MERGE",
            "GRANT",
            "REVOKE",
        ]

        upper_sql = query.upper()

        for keyword in forbidden_keywords:

            pattern = rf"\b{keyword}\b"

            if re.search(pattern, upper_sql):

                raise ValueError(
                    f"SQL keyword '{keyword}' is not allowed"
                )

    # =====================================================
    # EXECUTE
    # =====================================================

    def execute(self, sql: str):

        # ---------------------------------------------
        # VALIDATE
        # ---------------------------------------------

        self.validate_sql(sql)

        connector = SQLServerConnector(
            self.config
        )

        connection = None
        cursor = None

        try:

            # -----------------------------------------
            # CONNECT
            # -----------------------------------------

            connection = connector.connect()

            cursor = connection.cursor()

            # -----------------------------------------
            # EXECUTE
            # -----------------------------------------

            cursor.execute(sql)

            # -----------------------------------------
            # COLUMNS
            # -----------------------------------------

            columns = []

            if cursor.description:

                columns = [
                    column[0]
                    for column in cursor.description
                ]

            # -----------------------------------------
            # ROWS
            # -----------------------------------------

            rows = []

            if cursor.description:

                fetched_rows = cursor.fetchall()

                for row in fetched_rows:

                    row_dict = {}

                    for index, column in enumerate(columns):

                        value = row[index]

                        row_dict[column] = value

                    rows.append(row_dict)

            # -----------------------------------------
            # RETURN
            # -----------------------------------------

            return {
                "success": True,
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
            }

        finally:

            if cursor:

                cursor.close()

            connector.close()