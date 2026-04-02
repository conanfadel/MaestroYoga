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


def _public_users_is_deleted_sql(dialect: str) -> str:
    if dialect == "postgresql":
        return "ALTER TABLE public_users ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE"
    return "ALTER TABLE public_users ADD COLUMN is_deleted BOOLEAN DEFAULT 0"


def _public_users_deleted_at_sql(dialect: str) -> str:
    if dialect == "postgresql":
        return "ALTER TABLE public_users ADD COLUMN deleted_at TIMESTAMP"
    return "ALTER TABLE public_users ADD COLUMN deleted_at DATETIME"


def _ensure_performance_indexes(conn, insp) -> None:
    index_specs: list[tuple[str, str, str]] = [
        ("clients", "idx_clients_center_id", "center_id"),
        ("rooms", "idx_rooms_center_id", "center_id"),
        ("subscription_plans", "idx_subscription_plans_center_active", "center_id, is_active"),
        ("yoga_sessions", "idx_yoga_sessions_center_room_start", "center_id, room_id, starts_at"),
        ("bookings", "idx_bookings_center_session_status", "center_id, session_id, status"),
        ("bookings", "idx_bookings_session_id", "session_id"),
        ("payments", "idx_payments_center_status_paid_at", "center_id, status, paid_at"),
        ("payments", "idx_payments_booking_id", "booking_id"),
        ("payments", "idx_payments_client_id", "client_id"),
        ("client_subscriptions", "idx_client_subscriptions_status", "status"),
        ("client_subscriptions", "idx_client_subscriptions_client_id", "client_id"),
        ("client_subscriptions", "idx_client_subscriptions_plan_id", "plan_id"),
        ("public_users", "idx_public_users_created_at", "created_at"),
        ("security_audit_events", "idx_security_audit_created_status", "created_at, status"),
    ]
    for table_name, index_name, columns in index_specs:
        if insp.has_table(table_name):
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({columns})"))


def migrate_schema() -> None:
    """Lightweight migrations for existing SQLite/Postgres DBs."""
    dialect = engine.dialect.name
    insp = inspect(engine)
    has_payments = insp.has_table("payments")
    needs_payment_booking_id = False
    if has_payments:
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
        with engine.begin() as conn:
            _ensure_performance_indexes(conn, insp)
        return
    with engine.begin() as conn:
        if needs_payment_booking_id:
            conn.execute(text("ALTER TABLE payments ADD COLUMN booking_id INTEGER"))
        if needs_public_user_phone:
            conn.execute(text("ALTER TABLE public_users ADD COLUMN phone VARCHAR"))
        if needs_public_user_is_deleted:
            conn.execute(text(_public_users_is_deleted_sql(dialect)))
            if dialect == "postgresql":
                conn.execute(text("UPDATE public_users SET is_deleted = FALSE WHERE is_deleted IS NULL"))
            else:
                conn.execute(text("UPDATE public_users SET is_deleted = 0 WHERE is_deleted IS NULL"))
        if needs_public_user_deleted_at:
            conn.execute(text(_public_users_deleted_at_sql(dialect)))
        _ensure_performance_indexes(conn, insp)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    migrate_schema()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
