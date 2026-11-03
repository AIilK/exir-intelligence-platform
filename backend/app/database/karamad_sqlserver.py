import logging
import time
from functools import lru_cache
from urllib.parse import quote_plus

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


logger = logging.getLogger(__name__)
LOGIN_TIMEOUT_SECONDS = 30
CONNECT_ATTEMPTS = 3


@lru_cache(maxsize=1)
def get_karamad_sqlserver_engine() -> Engine:
    """Read-only SQL Server engine for the live Karamad database."""
    if not settings.KARAMAD_SQLSERVER_PASSWORD:
        raise RuntimeError("KARAMAD_SQLSERVER_PASSWORD is not configured in .env")

    trust_certificate = "yes" if settings.KARAMAD_SQLSERVER_TRUST_CERTIFICATE else "no"
    odbc_connection_string = (
        f"DRIVER={{{settings.KARAMAD_SQLSERVER_DRIVER}}};"
        f"SERVER={settings.KARAMAD_SQLSERVER_SERVER};"
        f"DATABASE={settings.KARAMAD_SQLSERVER_DATABASE};"
        f"UID={settings.KARAMAD_SQLSERVER_USERNAME};"
        f"PWD={settings.KARAMAD_SQLSERVER_PASSWORD};"
        "Encrypt=yes;"
        f"TrustServerCertificate={trust_certificate};"
        "ApplicationIntent=ReadOnly;"
    )
    connection_url = "mssql+pyodbc:///?odbc_connect=" + quote_plus(odbc_connection_string)
    # The shared Karamad server sometimes answers the login late when it is busy; wait longer
    # than the 15 s driver default and retry, instead of failing the page on one slow login.
    engine = create_engine(
        connection_url,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={"timeout": LOGIN_TIMEOUT_SECONDS},
    )

    @event.listens_for(engine, "do_connect")
    def _connect_with_retry(dialect, conn_rec, cargs, cparams):
        for attempt in range(1, CONNECT_ATTEMPTS + 1):
            try:
                return dialect.connect(*cargs, **cparams)
            except dialect.dbapi.OperationalError:
                if attempt == CONNECT_ATTEMPTS:
                    raise
                logger.warning("Karamad SQL login failed (attempt %s); retrying", attempt)
                time.sleep(2 * attempt)

    return engine


def get_karamad_sqlserver_session():
    session_factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=get_karamad_sqlserver_engine(),
    )
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
