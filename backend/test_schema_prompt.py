from app.database.session import SessionLocal

from app.query.schema_context import (
    SchemaContextBuilder
)

from app.query.schema_prompt import (
    SchemaPromptBuilder
)


db = SessionLocal()

try:

    # ==========================================
    # BUILD SCHEMA CONTEXT
    # ==========================================

    context_builder = SchemaContextBuilder(db)

    context = context_builder.build(
        connection_id=3,
        question="مشتری‌های تهران را نشان بده"
    )

    # ==========================================
    # BUILD PROMPT
    # ==========================================

    prompt_builder = SchemaPromptBuilder()

    prompt = prompt_builder.build(context)

    print()
    print("=" * 70)
    print("SCHEMA PROMPT")
    print("=" * 70)
    print()

    print(prompt)

finally:

    db.close()