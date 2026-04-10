"""Incremental ALTERs and indexes for existing SQLite/Postgres databases."""

from sqlalchemy import inspect, text

from .engine import engine
from .migrate_support import (
    _cleanup_stale_center_logo_urls_sql,
    _clear_legacy_default_hero_url,
    _ensure_performance_indexes,
    _public_users_deleted_at_sql,
    _public_users_is_deleted_sql,
)


def migrate_schema() -> None:
    """Lightweight migrations for existing SQLite/Postgres DBs."""
    dialect = engine.dialect.name
    insp = inspect(engine)
    has_payments = insp.has_table("payments")
    needs_payment_booking_id = False
    needs_payment_created_at = False
    if has_payments:
        payment_cols = {c["name"] for c in insp.get_columns("payments")}
        needs_payment_booking_id = "booking_id" not in payment_cols
        needs_payment_created_at = "created_at" not in payment_cols

    needs_booking_checked_in = False
    if insp.has_table("bookings"):
        booking_cols = {c["name"] for c in insp.get_columns("bookings")}
        needs_booking_checked_in = "checked_in" not in booking_cols

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
    needs_center_index_config_json = False
    needs_center_monthly_revenue_goal = False
    needs_center_monthly_bookings_goal = False
    needs_center_vat_rate_percent = False
    needs_center_report_digest_email = False
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
        needs_center_index_config_json = "index_config_json" not in center_cols
        needs_center_monthly_revenue_goal = "monthly_revenue_goal" not in center_cols
        needs_center_monthly_bookings_goal = "monthly_bookings_goal" not in center_cols
        needs_center_vat_rate_percent = "vat_rate_percent" not in center_cols
        needs_center_report_digest_email = "report_digest_email" not in center_cols

    needs_users_custom_role_label = False
    needs_users_permissions_json = False
    if insp.has_table("users"):
        user_cols = {c["name"] for c in insp.get_columns("users")}
        needs_users_custom_role_label = "custom_role_label" not in user_cols
        needs_users_permissions_json = "permissions_json" not in user_cols

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
        and not needs_center_index_config_json
        and not needs_center_monthly_revenue_goal
        and not needs_center_monthly_bookings_goal
        and not needs_center_vat_rate_percent
        and not needs_center_report_digest_email
        and not needs_users_custom_role_label
        and not needs_users_permissions_json
        and not needs_booking_checked_in
        and not needs_payment_created_at
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
        if needs_center_index_config_json:
            conn.execute(text("ALTER TABLE centers ADD COLUMN index_config_json TEXT"))
        if needs_center_monthly_revenue_goal:
            if dialect == "postgresql":
                conn.execute(text("ALTER TABLE centers ADD COLUMN monthly_revenue_goal DOUBLE PRECISION"))
            else:
                conn.execute(text("ALTER TABLE centers ADD COLUMN monthly_revenue_goal REAL"))
        if needs_center_monthly_bookings_goal:
            conn.execute(text("ALTER TABLE centers ADD COLUMN monthly_bookings_goal INTEGER"))
        if needs_center_vat_rate_percent:
            if dialect == "postgresql":
                conn.execute(text("ALTER TABLE centers ADD COLUMN vat_rate_percent DOUBLE PRECISION"))
            else:
                conn.execute(text("ALTER TABLE centers ADD COLUMN vat_rate_percent REAL"))
        if needs_center_report_digest_email:
            conn.execute(text("ALTER TABLE centers ADD COLUMN report_digest_email VARCHAR(220)"))
        if needs_users_custom_role_label:
            conn.execute(text("ALTER TABLE users ADD COLUMN custom_role_label VARCHAR(120)"))
        if needs_users_permissions_json:
            conn.execute(text("ALTER TABLE users ADD COLUMN permissions_json TEXT"))
        if needs_booking_checked_in:
            conn.execute(text("ALTER TABLE bookings ADD COLUMN checked_in BOOLEAN"))
        if needs_payment_created_at:
            if dialect == "postgresql":
                conn.execute(text("ALTER TABLE payments ADD COLUMN created_at TIMESTAMP"))
            else:
                conn.execute(text("ALTER TABLE payments ADD COLUMN created_at DATETIME"))
            conn.execute(text("UPDATE payments SET created_at = paid_at WHERE created_at IS NULL"))
        _cleanup_stale_center_logo_urls_sql(conn)
        _clear_legacy_default_hero_url(conn, inspect(conn))
        _ensure_performance_indexes(conn, insp)
