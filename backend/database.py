from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from pathlib import Path
from dotenv import load_dotenv
import os

BACKEND_DIR = Path(__file__).parent

load_dotenv(BACKEND_DIR / ".env")

def normalize_database_url(database_url: str) -> str:
    """Resolve relative SQLite database paths from the backend directory."""

    url = make_url(database_url)
    if url.drivername.startswith("sqlite") and url.database and url.database != ":memory:":
        database_path = Path(url.database)
        if not database_path.is_absolute():
            url = url.set(database=str((BACKEND_DIR / database_path).resolve()))
    return url.render_as_string(hide_password=False)


DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set. Check your backend/.env file.")

DATABASE_URL = normalize_database_url(DATABASE_URL)

def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def configure_sqlite_foreign_keys(target_engine) -> bool:
    """Enable SQLite foreign keys once per engine; leave other dialects unchanged."""
    if target_engine.dialect.name != "sqlite":
        return False
    if getattr(target_engine, "_auroratio_sqlite_fk_configured", False):
        return True
    event.listen(target_engine, "connect", _enable_sqlite_foreign_keys)
    target_engine._auroratio_sqlite_fk_configured = True
    return True


engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
configure_sqlite_foreign_keys(engine)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
