import os

from sqlalchemy import create_engine, inspect, text
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


def _public_users_is_deleted_sql(dialect: str) -> str:
    if dialect == "postgresql":
        return "ALTER TABLE public_users ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE"
    return "ALTER TABLE public_users ADD COLUMN is_deleted BOOLEAN DEFAULT 0"


def _public_users_deleted_at_sql(dialect: str) -> str:
    if dialect == "postgresql":
        return "ALTER TABLE public_users ADD COLUMN deleted_at TIMESTAMP"
    return "ALTER TABLE public_users ADD COLUMN deleted_at DATETIME"


LEGACY_DEFAULT_CENTER_HERO_URL = "/static/branding/hero-default.svg"


def _cleanup_stale_center_logo_urls_sql(conn) -> None:
    """Clear DB references to removed default assets (e.g. maestro-logo.png)."""
    conn.execute(text("UPDATE centers SET logo_url = NULL WHERE logo_url LIKE '%maestro-logo%'"))


def _clear_legacy_default_hero_url(conn, insp) -> None:
    if not insp.has_table("centers"):
        return
    cols = {c["name"] for c in insp.get_columns("centers")}
    if "hero_image_url" not in cols:
        return
    conn.execute(
        text("UPDATE centers SET hero_image_url = NULL WHERE hero_image_url = :u"),
        {"u": LEGACY_DEFAULT_CENTER_HERO_URL},
    )


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
        ("center_posts", "idx_center_posts_center_published_pinned", "center_id, is_published, is_pinned"),
        ("center_posts", "idx_center_posts_published_at", "published_at"),
        ("center_post_images", "idx_center_post_images_post_id", "post_id"),
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

    needs_center_logo_url = False
    needs_center_brand_tagline = False
    needs_center_hero_image_url = False
    needs_center_hero_show_stock_photo = False
    needs_center_loyalty_bronze = False
    needs_center_loyalty_silver = False
    needs_center_loyalty_gold = False
    needs_center_loyalty_lb = False
    needs_center_loyalty_ls = False
    needs_center_loyalty_lg = False
    needs_center_loyalty_rb = False
    needs_center_loyalty_rs = False
    needs_center_loyalty_rg = False
    if insp.has_table("centers"):
        center_cols = {c["name"] for c in insp.get_columns("centers")}
        needs_center_logo_url = "logo_url" not in center_cols
        needs_center_brand_tagline = "brand_tagline" not in center_cols
        needs_center_hero_image_url = "hero_image_url" not in center_cols
        needs_center_hero_show_stock_photo = "hero_show_stock_photo" not in center_cols
        needs_center_loyalty_bronze = "loyalty_bronze_min" not in center_cols
        needs_center_loyalty_silver = "loyalty_silver_min" not in center_cols
        needs_center_loyalty_gold = "loyalty_gold_min" not in center_cols
        needs_center_loyalty_lb = "loyalty_label_bronze" not in center_cols
        needs_center_loyalty_ls = "loyalty_label_silver" not in center_cols
        needs_center_loyalty_lg = "loyalty_label_gold" not in center_cols
        needs_center_loyalty_rb = "loyalty_reward_bronze" not in center_cols
        needs_center_loyalty_rs = "loyalty_reward_silver" not in center_cols
        needs_center_loyalty_rg = "loyalty_reward_gold" not in center_cols

    if (
        not needs_payment_booking_id
        and not needs_public_user_phone
        and not needs_public_user_is_deleted
        and not needs_public_user_deleted_at
        and not needs_center_logo_url
        and not needs_center_brand_tagline
        and not needs_center_hero_image_url
        and not needs_center_hero_show_stock_photo
        and not needs_center_loyalty_bronze
        and not needs_center_loyalty_silver
        and not needs_center_loyalty_gold
        and not needs_center_loyalty_lb
        and not needs_center_loyalty_ls
        and not needs_center_loyalty_lg
        and not needs_center_loyalty_rb
        and not needs_center_loyalty_rs
        and not needs_center_loyalty_rg
    ):
        with engine.begin() as conn:
            _cleanup_stale_center_logo_urls_sql(conn)
            _clear_legacy_default_hero_url(conn, insp)
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
        if needs_center_logo_url:
            conn.execute(text("ALTER TABLE centers ADD COLUMN logo_url VARCHAR"))
        if needs_center_brand_tagline:
            conn.execute(text("ALTER TABLE centers ADD COLUMN brand_tagline VARCHAR"))
        if needs_center_hero_image_url:
            conn.execute(text("ALTER TABLE centers ADD COLUMN hero_image_url VARCHAR"))
        if needs_center_hero_show_stock_photo:
            if dialect == "postgresql":
                conn.execute(
                    text("ALTER TABLE centers ADD COLUMN hero_show_stock_photo BOOLEAN NOT NULL DEFAULT TRUE")
                )
            else:
                conn.execute(text("ALTER TABLE centers ADD COLUMN hero_show_stock_photo BOOLEAN DEFAULT 1"))
                conn.execute(text("UPDATE centers SET hero_show_stock_photo = 1 WHERE hero_show_stock_photo IS NULL"))
        if needs_center_loyalty_bronze:
            conn.execute(text("ALTER TABLE centers ADD COLUMN loyalty_bronze_min INTEGER"))
        if needs_center_loyalty_silver:
            conn.execute(text("ALTER TABLE centers ADD COLUMN loyalty_silver_min INTEGER"))
        if needs_center_loyalty_gold:
            conn.execute(text("ALTER TABLE centers ADD COLUMN loyalty_gold_min INTEGER"))
        if needs_center_loyalty_lb:
            conn.execute(text("ALTER TABLE centers ADD COLUMN loyalty_label_bronze VARCHAR(64)"))
        if needs_center_loyalty_ls:
            conn.execute(text("ALTER TABLE centers ADD COLUMN loyalty_label_silver VARCHAR(64)"))
        if needs_center_loyalty_lg:
            conn.execute(text("ALTER TABLE centers ADD COLUMN loyalty_label_gold VARCHAR(64)"))
        if needs_center_loyalty_rb:
            conn.execute(text("ALTER TABLE centers ADD COLUMN loyalty_reward_bronze TEXT"))
        if needs_center_loyalty_rs:
            conn.execute(text("ALTER TABLE centers ADD COLUMN loyalty_reward_silver TEXT"))
        if needs_center_loyalty_rg:
            conn.execute(text("ALTER TABLE centers ADD COLUMN loyalty_reward_gold TEXT"))
        _cleanup_stale_center_logo_urls_sql(conn)
        _clear_legacy_default_hero_url(conn, inspect(conn))
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
