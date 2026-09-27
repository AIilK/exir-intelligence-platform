from app.database.sqlserver import get_sqlserver_engine
from sqlalchemy import text


engine = get_sqlserver_engine()

with engine.connect() as conn:
    result = conn.execute(
        text("SELECT TOP 5 * FROM FIN3.Account")
    )

    for row in result:
        print(row)
