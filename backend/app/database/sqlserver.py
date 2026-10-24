from functools import lru_cache
from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


@lru_cache(maxsize=1)
def get_sqlserver_engine() -> Engine:
    """یک Engine مشترک و امن برای دیتابیس Read-only راهکاران می‌سازد."""

    if not settings.SQLSERVER_PASSWORD:
        raise RuntimeError(
            "SQLSERVER_PASSWORD is not configured in .env"
        )

    trust_certificate = (
        "yes"
        if settings.SQLSERVER_TRUST_CERTIFICATE
        else "no"
    )

    odbc_connection_string = (
        f"DRIVER={{{settings.SQLSERVER_DRIVER}}};"
        f"SERVER={settings.SQLSERVER_SERVER};"
        f"DATABASE={settings.SQLSERVER_DATABASE};"
        f"UID={settings.SQLSERVER_USERNAME};"
        f"PWD={settings.SQLSERVER_PASSWORD};"
        "Encrypt=yes;"
        f"TrustServerCertificate={trust_certificate};"
        "ApplicationIntent=ReadOnly;"
    )

    connection_url = (
        "mssql+pyodbc:///?odbc_connect="
        + quote_plus(odbc_connection_string)
    )

    return create_engine(
        connection_url,
        pool_pre_ping=True,
        pool_recycle=1800,
    )


def get_sqlserver_session():
    session_factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=get_sqlserver_engine(),
    )

    db = session_factory()
    try:
        yield db
    finally:
        db.close()
