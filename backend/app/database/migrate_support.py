"""Helpers for lightweight schema migration and index creation."""

import json

from sqlalchemy import text


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
    if insp.has_table("bookings"):
        try:
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_bookings_active_session_client "
                    "ON bookings (session_id, client_id) "
                    "WHERE status IN ('booked','confirmed','pending_payment')"
                )
            )
        except Exception:
            # Existing duplicate active rows can block index creation on old data sets.
            pass


_INDEX_PC_TEAM_HIDE_PATCH_ID = "index_pc_team_default_hide_v1"


def _ensure_maestro_schema_patches_table(conn) -> None:
    conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS maestro_schema_patches (patch_id VARCHAR(128) NOT NULL PRIMARY KEY)"
        )
    )


def _apply_patch_index_hide_product_clarity_and_team_strip(conn, insp) -> None:
    """One-time: stored index_config_json may still have show=true from old defaults; align with new policy."""
    if not insp.has_table("centers"):
        return
    _ensure_maestro_schema_patches_table(conn)
    if conn.execute(
        text("SELECT 1 FROM maestro_schema_patches WHERE patch_id = :p"),
        {"p": _INDEX_PC_TEAM_HIDE_PATCH_ID},
    ).first():
        return
    rows = conn.execute(
        text(
            "SELECT id, index_config_json FROM centers "
            "WHERE index_config_json IS NOT NULL AND trim(index_config_json) <> ''"
        )
    ).fetchall()
    for row in rows:
        cid, raw = int(row[0]), row[1]
        if not raw or not str(raw).strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        changed = False
        for key in ("product_clarity", "team_strip"):
            block = data.get(key)
            if isinstance(block, dict) and block.get("show") is True:
                block["show"] = False
                changed = True
        if changed:
            conn.execute(
                text("UPDATE centers SET index_config_json = :blob WHERE id = :id"),
                {
                    "blob": json.dumps(data, ensure_ascii=False),
                    "id": cid,
                },
            )
    conn.execute(
        text("INSERT INTO maestro_schema_patches (patch_id) VALUES (:p)"),
        {"p": _INDEX_PC_TEAM_HIDE_PATCH_ID},
    )
