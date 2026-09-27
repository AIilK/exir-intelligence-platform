from typing import Any


class SQLServerConnector:

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.connection = None

    # =====================================================
    # CONNECT
    # =====================================================

    def connect(self):

        try:
            import pyodbc
        except ImportError as exc:
            raise RuntimeError(
                "pyodbc نصب نشده است؛ pip install pyodbc را اجرا کنید."
            ) from exc

        server = self.config["server"]
        database = self.config["database"]
        auth_type = self.config.get("auth_type", "sql")
        driver = self.config.get("driver", "ODBC Driver 18 for SQL Server")
        trust_certificate = "yes" if self.config.get("trust_certificate", True) else "no"
        encrypt = "yes" if self.config.get("encrypt", True) else "no"

        if auth_type == "windows":

            connection_string = (
                f"DRIVER={{{driver}}};"
                f"SERVER={server};"
                f"DATABASE={database};"
                "Trusted_Connection=yes;"
                f"Encrypt={encrypt};"
                f"TrustServerCertificate={trust_certificate};"
            )

        else:

            username = self.config["username"]
            password = self.config["password"]

            connection_string = (
                f"DRIVER={{{driver}}};"
                f"SERVER={server};"
                f"DATABASE={database};"
                f"UID={username};"
                f"PWD={password};"
                f"Encrypt={encrypt};"
                f"TrustServerCertificate={trust_certificate};"
                "ApplicationIntent=ReadOnly;"
            )

        self.connection = pyodbc.connect(
            connection_string
        )

        return self.connection

    # =====================================================
    # CLOSE
    # =====================================================

    def close(self):

        if self.connection:

            self.connection.close()
            self.connection = None

    # =====================================================
    # TEST CONNECTION
    # =====================================================

    def test_connection(self):

        try:

            connection = self.connect()

            cursor = connection.cursor()

            cursor.execute("SELECT 1")

            result = cursor.fetchone()

            cursor.close()

            self.close()

            return {
                "success": True,
                "result": result[0]
            }

        except Exception as e:

            self.close()

            return {
                "success": False,
                "error": str(e)
            }

    # =====================================================
    # GET SCHEMA
    # =====================================================

    def get_schema(self):

        try:

            connection = self.connect()

            cursor = connection.cursor()

            schema = {}

            # =================================================
            # 1. TABLES
            # =================================================

            cursor.execute("""
                SELECT
                    TABLE_SCHEMA,
                    TABLE_NAME
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_TYPE = 'BASE TABLE'
                ORDER BY
                    TABLE_SCHEMA,
                    TABLE_NAME
            """)

            tables = cursor.fetchall()

            # =================================================
            # 2. COLUMNS
            # =================================================

            for table in tables:

                schema_name = table[0]
                table_name = table[1]

                schema[table_name] = {
                    "schema_name": schema_name,
                    "columns": [],
                    "primary_keys": [],
                    "foreign_keys": []
                }

                cursor.execute("""
                    SELECT
                        COLUMN_NAME,
                        DATA_TYPE,
                        IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = ?
                    AND TABLE_NAME = ?
                    ORDER BY ORDINAL_POSITION
                """, schema_name, table_name)

                columns = cursor.fetchall()

                for column in columns:

                    schema[table_name]["columns"].append({

                        "name": column[0],

                        "type": column[1],

                        "nullable": column[2] == "YES"

                    })

            # =================================================
            # 3. PRIMARY KEYS
            # =================================================

            cursor.execute("""
                SELECT
                    ku.TABLE_SCHEMA,
                    ku.TABLE_NAME,
                    ku.COLUMN_NAME

                FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE ku

                INNER JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc

                    ON ku.CONSTRAINT_NAME =
                       tc.CONSTRAINT_NAME

                    AND ku.TABLE_SCHEMA =
                        tc.TABLE_SCHEMA

                    AND ku.TABLE_NAME =
                        tc.TABLE_NAME

                WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'

                ORDER BY
                    ku.TABLE_SCHEMA,
                    ku.TABLE_NAME,
                    ku.ORDINAL_POSITION
            """)

            primary_keys = cursor.fetchall()

            for row in primary_keys:

                schema_name = row[0]
                table_name = row[1]
                column_name = row[2]

                if table_name in schema:

                    schema[table_name][
                        "primary_keys"
                    ].append(column_name)

            # =================================================
            # 4. FOREIGN KEYS
            # =================================================

            cursor.execute("""
                SELECT

                    OBJECT_SCHEMA_NAME(
                        fkc.parent_object_id
                    ) AS source_schema,

                    OBJECT_NAME(
                        fkc.parent_object_id
                    ) AS source_table,

                    COL_NAME(
                        fkc.parent_object_id,
                        fkc.parent_column_id
                    ) AS source_column,

                    OBJECT_SCHEMA_NAME(
                        fkc.referenced_object_id
                    ) AS target_schema,

                    OBJECT_NAME(
                        fkc.referenced_object_id
                    ) AS target_table,

                    COL_NAME(
                        fkc.referenced_object_id,
                        fkc.referenced_column_id
                    ) AS target_column

                FROM sys.foreign_key_columns fkc

                INNER JOIN sys.foreign_keys fk

                    ON fkc.constraint_object_id =
                       fk.object_id

                ORDER BY

                    source_schema,
                    source_table,
                    source_column
            """)

            foreign_keys = cursor.fetchall()

            for row in foreign_keys:

                source_schema = row[0]
                source_table = row[1]
                source_column = row[2]

                target_schema = row[3]
                target_table = row[4]
                target_column = row[5]

                if source_table not in schema:

                    continue

                schema[source_table][
                    "foreign_keys"
                ].append({

                    "column": source_column,

                    "references_schema": target_schema,

                    "references_table": target_table,

                    "references_column": target_column

                })

            # =================================================
            # CLOSE
            # =================================================

            cursor.close()

            self.close()

            # =================================================
            # RETURN
            # =================================================

            return {

                "success": True,

                "database": self.config["database"],

                "schema": schema

            }

        except Exception as e:

            self.close()

            return {

                "success": False,

                "error": str(e)

            }

    # =====================================================
    # EXECUTE QUERY
    # =====================================================

    def execute_query(self, sql: str):

        try:

            connection = self.connect()

            cursor = connection.cursor()

            # -------------------------------------------------
            # Execute SQL
            # -------------------------------------------------

            cursor.execute(sql)

            # -------------------------------------------------
            # اگر Query نتیجه نداشته باشد
            # -------------------------------------------------

            if cursor.description is None:

                connection.commit()

                cursor.close()

                self.close()

                return {
                    "success": True,
                    "columns": [],
                    "rows": [],
                    "row_count": 0
                }

            # -------------------------------------------------
            # دریافت نام ستون‌ها
            # -------------------------------------------------

            columns = [
                column[0]
                for column in cursor.description
            ]

            # -------------------------------------------------
            # دریافت داده‌ها
            # -------------------------------------------------

            raw_rows = cursor.fetchall()

            # -------------------------------------------------
            # تبدیل Row به Dictionary
            # -------------------------------------------------

            rows = []

            for row in raw_rows:

                row_data = {}

                for index, column_name in enumerate(columns):

                    row_data[column_name] = row[index]

                rows.append(row_data)

            # -------------------------------------------------
            # Close
            # -------------------------------------------------

            cursor.close()

            self.close()

            # -------------------------------------------------
            # Return
            # -------------------------------------------------

            return {

                "success": True,

                "columns": columns,

                "rows": rows,

                "row_count": len(rows)

            }

        except Exception as e:

            self.close()

            return {

                "success": False,

                "columns": [],

                "rows": [],

                "row_count": 0,

                "error": str(e)

            }