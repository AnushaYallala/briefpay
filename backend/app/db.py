"""SQLAlchemy engine/session. Portable: PostgreSQL in prod, SQLite for local dev/tests (D-002)."""
from collections.abc import Iterator
import sqlite3

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def make_engine(url: str | None = None) -> Engine:
    s = get_settings()
    url = url or s.database_url
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30.0}
    elif s.database_ssl_ca:
        kwargs["connect_args"] = {"sslrootcert": s.database_ssl_ca}
    eng = create_engine(url, **kwargs)
    if url.startswith("sqlite") and ":memory:" not in url:
        @event.listens_for(eng, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            if isinstance(dbapi_connection, sqlite3.Connection):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=30000")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.close()
    return eng


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
