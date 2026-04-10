"""SQLAlchemy engine, session factory, and declarative Base."""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./maestro_yoga.db")
is_sqlite = DATABASE_URL.startswith("sqlite")

_engine_kwargs: dict = {}
if is_sqlite:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    try:
        _db_timeout = max(5, int(os.getenv("DB_CONNECT_TIMEOUT", "15")))
    except ValueError:
        _db_timeout = 15
    _engine_kwargs["connect_args"] = {"connect_timeout": _db_timeout}
    _engine_kwargs["pool_pre_ping"] = True

engine = create_engine(DATABASE_URL, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
