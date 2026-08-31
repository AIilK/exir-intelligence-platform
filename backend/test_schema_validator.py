from app.database.session import SessionLocal

from app.query.schema_context import (
    SchemaContextBuilder
)

from app.query.schema_validator import (
    SchemaValidator
)


db = SessionLocal()

try:

    context_builder = SchemaContextBuilder(db)

    context = context_builder.build(
        connection_id=3,
        question="مشتری‌های تهران را نشان بده"
    )

    validator = SchemaValidator()

    tests = [

        "SELECT id, name FROM dbo.customers",

        "SELECT TOP 10 * FROM dbo.customers",

        "SELECT id, salary FROM dbo.customers",

        "SELECT id FROM dbo.unknown_table",

    ]

    for sql in tests:

        result = validator.validate(
            sql,
            context
        )

        print()
        print("=" * 60)

        print("SQL:")
        print(sql)

        print()

        print("RESULT:")
        print(result)

finally:

    db.close()