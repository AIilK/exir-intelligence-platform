from app.database.session import SessionLocal
from app.query.service import QueryService


db = SessionLocal()

try:

    service = QueryService()

    result = service.generate_sql(
        db=db,
        connection_id=3,
        question="مشتری‌های تهران را نشان بده",
    )

    print()
    print("=" * 60)
    print("QUERY SERVICE RESULT")
    print("=" * 60)

    print(result)

finally:

    db.close()