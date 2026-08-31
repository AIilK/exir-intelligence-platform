from app.database.session import SessionLocal
from app.query.service import QueryService


db = SessionLocal()

try:

    service = QueryService()

    result = service.execute_question(
        db=db,
        connection_id=3,
        question="مشتری‌های تهران را نشان بده",
    )

    print("=" * 60)
    print("EXECUTE QUESTION RESULT")
    print("=" * 60)

    print(result)

finally:

    db.close()