import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./maestro_yoga.db")
is_sqlite = DATABASE_URL.startswith("sqlite")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if is_sqlite else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def migrate_schema() -> None:
    """Lightweight migrations for existing SQLite/Postgres DBs."""
    insp = inspect(engine)
    if not insp.has_table("payments"):
        return
    payment_cols = {c["name"] for c in insp.get_columns("payments")}
    needs_payment_booking_id = "booking_id" not in payment_cols

    needs_public_user_phone = False
    needs_public_user_is_deleted = False
    needs_public_user_deleted_at = False
    if insp.has_table("public_users"):
        public_user_cols = {c["name"] for c in insp.get_columns("public_users")}
        needs_public_user_phone = "phone" not in public_user_cols
        needs_public_user_is_deleted = "is_deleted" not in public_user_cols
        needs_public_user_deleted_at = "deleted_at" not in public_user_cols

    if (
        not needs_payment_booking_id
        and not needs_public_user_phone
        and not needs_public_user_is_deleted
        and not needs_public_user_deleted_at
    ):
        return
    with engine.begin() as conn:
        if needs_payment_booking_id:
            conn.execute(text("ALTER TABLE payments ADD COLUMN booking_id INTEGER"))
        if needs_public_user_phone:
            conn.execute(text("ALTER TABLE public_users ADD COLUMN phone VARCHAR"))
        if needs_public_user_is_deleted:
            conn.execute(text("ALTER TABLE public_users ADD COLUMN is_deleted BOOLEAN DEFAULT 0"))
            conn.execute(text("UPDATE public_users SET is_deleted = 0 WHERE is_deleted IS NULL"))
        if needs_public_user_deleted_at:
            conn.execute(text("ALTER TABLE public_users ADD COLUMN deleted_at DATETIME"))


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    migrate_schema()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
