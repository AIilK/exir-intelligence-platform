from typing import Any

from app.query.schema_prompt import SchemaPromptBuilder


class SQLGenerator:

    def __init__(self, llm_client):

        self.llm_client = llm_client
        self.prompt_builder = SchemaPromptBuilder()

    # =====================================================
    # GENERATE SQL
    # =====================================================

    def generate(
        self,
        context: dict[str, Any],
    ) -> str:

        # ---------------------------------------------
        # Build schema prompt
        # ---------------------------------------------

        schema_prompt = self.prompt_builder.build(
            context
        )

        # ---------------------------------------------
        # Build SQL generation prompt
        # ---------------------------------------------

        prompt = self._build_sql_prompt(
            schema_prompt
        )

        # ---------------------------------------------
        # Send to LLM
        # ---------------------------------------------

        response = self.llm_client.generate(
            prompt
        )

        # ---------------------------------------------
        # Clean response
        # ---------------------------------------------

        sql = self._clean_sql(response)

        return sql

    # =====================================================
    # BUILD PROMPT
    # =====================================================

    def _build_sql_prompt(
        self,
        schema_prompt: str,
    ) -> str:

        return f"""
You are an expert SQL Server query generator.

Your task is to convert the user's question
into a valid SQL Server SELECT query.

IMPORTANT RULES:

1. Return ONLY SQL.
2. Do NOT return Markdown.
3. Do NOT use ```sql.
4. Only SELECT queries are allowed.
5. Never generate INSERT.
6. Never generate UPDATE.
7. Never generate DELETE.
8. Never generate DROP.
9. Never generate ALTER.
10. Never generate TRUNCATE.
11. Use only tables and columns from the provided schema.
12. Use SQL Server syntax.
13. Use schema-qualified table names.
14. If the question requires a relationship,
    use the provided relationships.
15. Do not invent tables.
16. Do not invent columns.
17. For text values in SQL Server use N'...'.
18. Prefer TOP 100 unless the user asks for another limit.

DATABASE INFORMATION:

{schema_prompt}

Return ONLY the SQL query.
"""

    # =====================================================
    # CLEAN SQL
    # =====================================================

    def _clean_sql(
        self,
        response: str,
    ) -> str:

        sql = response.strip()

        # Remove Markdown code fences
        if sql.startswith("```sql"):

            sql = sql[6:]

        elif sql.startswith("```"):

            sql = sql[3:]

        if sql.endswith("```"):

            sql = sql[:-3]

        sql = sql.strip()

        return sql