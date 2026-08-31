from app.database.session import SessionLocal

from app.query.schema_context import (
    SchemaContextBuilder,
)


db = SessionLocal()

try:

    builder = SchemaContextBuilder(db)

    context = builder.build(
        connection_id=3,
        question="customer",
    )

    print("\n==============================")
    print("SCHEMA CONTEXT")
    print("==============================")

    print(context)

finally:

    db.close()