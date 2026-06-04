from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

_db_url = settings.DATABASE_URL
# Resolve relative sqlite paths against the project root (where this file lives: app/)
if _db_url.startswith("sqlite:///./") or _db_url == "sqlite:///./chemrepro.db":
    _project_root = Path(__file__).parent.parent
    _db_path = _project_root / "chemrepro.db"
    _db_url = f"sqlite:///{_db_path}"

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
