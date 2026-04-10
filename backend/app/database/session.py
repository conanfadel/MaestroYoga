"""Application session dependency and initial table creation."""

from .engine import Base, SessionLocal, engine
from .migrate import migrate_schema


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    migrate_schema()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
