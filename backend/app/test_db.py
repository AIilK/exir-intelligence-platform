from app.database.sqlserver import get_sqlserver_engine
from sqlalchemy import text


def main() -> None:
    """تست دستی اتصال؛ هنگام کشف تست‌های واحد اجرا نمی‌شود."""

    engine = get_sqlserver_engine()
    with engine.connect() as conn:
        result = conn.execute(text("SELECT TOP 5 * FROM FIN3.Account"))
        for row in result:
            print(row)


if __name__ == "__main__":
    main()
