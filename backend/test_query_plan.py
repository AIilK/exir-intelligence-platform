from app.database.session import SessionLocal
from app.query.service import QueryService


def main():

    db = SessionLocal()

    try:

        service = QueryService()

        result = service.build_query_plan(
            db=db,
            connection_id=3,
            question="فروش محصولات به مشتری‌های تهران را نشان بده",
        )

        print()
        print("=" * 60)
        print("QUERY PLAN RESULT")
        print("=" * 60)

        print(result)

    finally:

        db.close()


if __name__ == "__main__":
    main()