from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

_db_url = settings.DATABASE_URL

if _db_url.startswith("sqlite:///./") or _db_url == "sqlite:///./chemrepro.db":
    # Resolve relative SQLite path against the project root
    _project_root = Path(__file__).parent.parent
    _db_url = f"sqlite:///{_project_root / 'chemrepro.db'}"
elif _db_url.startswith("postgres://") or _db_url.startswith("postgresql://"):
    # Railway provides postgres:// — psycopg3 requires postgresql+psycopg://
    _db_url = _db_url.replace("postgres://", "postgresql+psycopg://", 1)
    _db_url = _db_url.replace("postgresql://", "postgresql+psycopg://", 1)

_connect_args = {"check_same_thread": False} if _db_url.startswith("sqlite") else {}
engine = create_engine(_db_url, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
