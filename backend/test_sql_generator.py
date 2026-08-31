from app.database.session import SessionLocal

from app.query.schema_context import (
    SchemaContextBuilder
)

from app.query.sql_generator import (
    SQLGenerator
)

from app.llm.mock_client import (
    MockLLMClient
)


db = SessionLocal()

try:

    # ==========================================
    # 1. BUILD CONTEXT
    # ==========================================

    context_builder = SchemaContextBuilder(db)

    context = context_builder.build(
        connection_id=3,
        question="مشتری‌های تهران را نشان بده"
    )

    # ==========================================
    # 2. CREATE LLM
    # ==========================================

    llm_client = MockLLMClient()

    # ==========================================
    # 3. CREATE SQL GENERATOR
    # ==========================================

    generator = SQLGenerator(
        llm_client
    )

    # ==========================================
    # 4. GENERATE SQL
    # ==========================================

    sql = generator.generate(
        context
    )

    # ==========================================
    # 5. PRINT
    # ==========================================

    print()
    print("=" * 70)
    print("GENERATED SQL")
    print("=" * 70)
    print()

    print(sql)

finally:

    db.close()