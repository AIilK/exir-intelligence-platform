import re


class SQLValidator:

    FORBIDDEN_KEYWORDS = [
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "ALTER",
        "TRUNCATE",
        "CREATE",
        "MERGE",
        "EXEC",
        "EXECUTE",
    ]

    def validate(self, sql: str) -> dict:

        if not sql:
            return {
                "valid": False,
                "reason": "SQL is empty",
            }

        sql = sql.strip()

        # ==========================================
        # فقط SELECT
        # ==========================================

        if not re.match(
            r"^SELECT\b",
            sql,
            re.IGNORECASE,
        ):
            return {
                "valid": False,
                "reason": "Only SELECT queries are allowed",
            }

        # ==========================================
        # جلوگیری از چند Statement
        # ==========================================

        statements = [
            statement.strip()
            for statement in sql.split(";")
            if statement.strip()
        ]

        if len(statements) > 1:

            return {
                "valid": False,
                "reason": "Multiple SQL statements are not allowed",
            }

        # ==========================================
        # بررسی دستورات خطرناک
        # ==========================================

        upper_sql = sql.upper()

        for keyword in self.FORBIDDEN_KEYWORDS:

            pattern = rf"\b{keyword}\b"

            if re.search(pattern, upper_sql):

                return {
                    "valid": False,
                    "reason": (
                        f"Forbidden SQL keyword: {keyword}"
                    ),
                }

        # ==========================================
        # موفق
        # ==========================================

        return {
            "valid": True,
            "reason": None,
        }